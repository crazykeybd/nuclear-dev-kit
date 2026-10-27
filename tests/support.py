#!/usr/bin/env python3
"""回归测试公共设施：CLI 调用、临时项目与完整七阶段夹具。

夹具中的批准文件只存在于临时目录，用于验证门禁行为，不是真实批准。
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "nuclear-dev" / "scripts"
CTL = SCRIPTS / "nuclearctl.py"
INSTALL = REPO / "skills" / "nuclear-setup" / "scripts" / "install.py"
QUICKINSTALL = REPO / "skills" / "nuclear-install" / "scripts" / "quickinstall.py"
REGISTER = REPO / "skills" / "nuclear-install" / "scripts" / "register.py"
BUILD_DIST = REPO / "tools" / "build_dist.py"
MCP = SCRIPTS / "nuclearmcp.py"
AUDIT = SCRIPTS / "nuclearaudit.py"
A2A = SCRIPTS / "nucleara2a.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import nuclearlib  # noqa: E402  （路径注入后才能导入冻结内核）

FIXED_TIME = "2026-10-26T00:00:00Z"
STAGES = ["plan", "requirements", "design", "implementation", "test", "vv", "release"]
STAGE_ARTIFACTS = {
    "plan": "stages/plan/plan.json",
    "requirements": "stages/requirements/requirements.json",
    "design": "stages/design/design.json",
    "implementation": "stages/implementation/implementation.json",
    "test": "stages/test/test-report.json",
    "vv": "stages/vv/vv-report.json",
    "release": "stages/release/release.json",
}

# 键 -> (项目内相对路径, 证据类型)
EVIDENCE_FILES = [
    ("build", "evidence/build.log", "build-log"),
    ("unit", "evidence/unit.log", "test-log"),
    ("model", "evidence/model.log", "test-log"),
    ("system", "evidence/system.log", "test-log"),
    ("conservation", "evidence/conservation.log", "test-log"),
    ("boundary", "evidence/boundary.log", "test-log"),
    ("negative", "evidence/negative.log", "test-log"),
    ("regression", "evidence/regression.log", "regression-log"),
    ("code_verification", "evidence/code-verification.log", "vv-report"),
    ("solution_verification", "evidence/solution-verification.log", "vv-report"),
    ("validation", "evidence/validation.log", "vv-report"),
    ("sbom", "evidence/sbom.json", "sbom"),
    ("reproducibility", "evidence/reproducibility.log", "release-check"),
    ("rollback", "evidence/rollback.log", "release-check"),
]


_ISOLATED_HOME: Optional[tempfile.TemporaryDirectory] = None


def isolated_home() -> Path:
    """整轮测试共用的临时 home；运行期由 atexit 清理。"""
    global _ISOLATED_HOME
    if _ISOLATED_HOME is None:
        _ISOLATED_HOME = tempfile.TemporaryDirectory(prefix="ndk-test-home-")
        atexit.register(_ISOLATED_HOME.cleanup)
    return Path(_ISOLATED_HOME.name)


def child_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    # 把每个子进程的用户目录指向临时 home：任何用例即使忘了传 --project / REASONIX_HOME，
    # 也不会读写开发者真实的 %APPDATA%\reasonix 或 ~/.claude。需要特定目录的用例在其后覆盖。
    home = isolated_home()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["APPDATA"] = str(home / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env.pop("REASONIX_HOME", None)
    env.pop("CODEX_HOME", None)
    return env


def run_script(
    script: Path,
    argv: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)] + list(argv),
        cwd=str(cwd) if cwd is not None else None,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env or child_env(),
    )


def parse_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        value = json.loads(stripped)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def ctl(root: Path, *argv: str) -> Tuple[int, Dict[str, Any], str]:
    completed = run_script(CTL, ["--root", str(root)] + [str(item) for item in argv])
    return completed.returncode, parse_json(completed.stdout), completed.stderr


def run_install(project: Path, *argv: str) -> Tuple[int, Dict[str, Any], str]:
    completed = run_script(INSTALL, ["--project", str(project)] + [str(item) for item in argv])
    return completed.returncode, parse_json(completed.stdout), completed.stderr


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return path


def with_write_retry(action: Callable[[], Any], attempts: int = 8, delay: float = 0.05) -> Any:
    """Windows 上杀毒或索引服务偶发短暂占用文件，测试夹具据此重试。"""
    for attempt in range(attempts):
        try:
            return action()
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
    raise AssertionError("不可达")


def write_json(path: Path, value: Any) -> Path:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return with_write_retry(lambda: write_text(path, payload))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- 夹具构造 -------------------------------------------------------

def _plan_artifact() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "project": {
            "name": "示例核能软件",
            "purpose": "验证七阶段门禁的回归测试夹具",
            "safety_classification": "安全重要",
            "classification_basis": "依据示例标准进行风险分级",
            "vv_level": "独立 V&V",
            "vv_basis": "策划要求独立验证与确认",
        },
        "standards": [
            {
                "id": "STD-001",
                "title": "示例核能软件开发标准",
                "revision": "2026",
                "applicability": "全流程",
                "status": "applicable",
                "source": "示例发布机构",
            }
        ],
        "vv_strategy": {
            "levels": ["代码验证", "解的验证", "确认"],
            "independence_required": True,
            "verification_methods": ["测试", "分析", "审查"],
            "validation_strategy": "以基准题确认适用范围",
        },
        "tool_qualification": [
            {
                "tool": "Python",
                "version": "3.11",
                "role": "构建与测试",
                "qualification_status": "qualified",
                "basis": "版本受控且经过回归验证",
                "limitations": "仅用于构建与测试",
            }
        ],
        "personnel": [
            {
                "role": "开发负责人",
                "required_qualification": "核工程背景",
                "assigned_person": "张三",
                "evidence": "资格记录-001",
                "status": "qualified",
            }
        ],
        "configuration_management": {
            "vcs": "git",
            "baseline": "1.0.0",
            "change_control": "变更单流程",
            "backup": "每日备份",
        },
        "open_items": [],
    }


def _requirements_artifact() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": {
            "description": "一维稳态导热求解",
            "applicability": "压水堆燃料棒稳态导热",
            "exclusions": [],
            "assumptions": ["物性恒定"],
            "limitations": ["未覆盖瞬态"],
        },
        "requirements": [
            {
                "id": "REQ-001",
                "title": "质量守恒",
                "statement": "离散格式必须逐单元守恒",
                "rationale": "物理守恒是结果可信的前提",
                "source": "示例标准 4.1",
                "priority": "critical",
                "safety_class": "安全重要",
                "category": "物理",
                "verification_method": "test",
                "validation_required": True,
                "acceptance_criteria": [
                    {
                        "id": "AC-001",
                        "criterion": "离散残差为零",
                        "method": "数值检查",
                        "tolerance": "1e-12",
                        "evidence_kind": "test-log",
                    }
                ],
                "status": "approved",
                "interfaces": [],
            }
        ],
        "open_items": [],
    }


def _design_artifact() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "architecture": {
            "overview": "有限体积求解器",
            "components": [
                {
                    "id": "CMP-001",
                    "name": "求解器核心",
                    "responsibility": "离散与求解",
                    "interfaces": ["solve()"],
                }
            ],
        },
        "models": [
            {
                "id": "MDL-001",
                "name": "稳态导热",
                "equations": ["d/dx(k dT/dx) = 0"],
                "assumptions": ["一维", "物性恒定"],
                "applicability": "稳态工况",
                "discretization": "有限体积",
                "stability": "隐式格式稳定",
                "conservation": "逐单元守恒",
                "error_analysis": "二阶中心差分",
            }
        ],
        "design_items": [
            {
                "id": "DES-001",
                "title": "守恒离散",
                "requirements": ["REQ-001"],
                "description": "有限体积离散",
                "algorithm": "面通量求和",
                "data_structures": "单元数组",
                "interfaces": ["solve()"],
                "error_control": "残差检查",
                "verification_plan": "与解析解对比",
                "status": "approved",
            }
        ],
        "open_items": [],
    }


def _implementation_artifact(evidence: Dict[str, str]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "source_control": {
            "repository": "example/nuclear-solver",
            "revision": "abc1234",
            "branch": "main",
            "dirty": False,
        },
        "build": {
            "system": "make",
            "compiler": "gcc",
            "compiler_version": "12.2",
            "flags": ["-O2"],
            "dependencies": ["python3"],
            "mpi": "none",
            "os": "Linux",
            "container": "none",
        },
        "modules": [
            {
                "id": "MOD-001",
                "title": "求解器模块",
                "design_ids": ["DES-001"],
                "paths": ["src/solver.py"],
                "language": "Python",
                "entrypoints": ["src/solver.py"],
                "unit_tests": ["tests/test_solver.py"],
                "static_analysis": "pyflakes",
                "status": "implemented",
            }
        ],
        "build_evidence_ids": [evidence["build"]],
        "open_items": [],
    }


def _test_report(evidence: Dict[str, str]) -> Dict[str, Any]:
    cases = [
        ("TEST-001", "单元级守恒检查", "unit", "unit"),
        ("TEST-002", "模型级解析解对比", "model", "model"),
        ("TEST-003", "系统级算例运行", "system", "system"),
        ("TEST-004", "守恒性检查", "system", "conservation"),
        ("TEST-005", "边界条件检查", "system", "boundary"),
        ("TEST-006", "负向输入检查", "system", "negative"),
    ]
    tests = []
    for identifier, title, level, category in cases:
        key = {
            "TEST-001": "unit",
            "TEST-002": "model",
            "TEST-003": "system",
            "TEST-004": "conservation",
            "TEST-005": "boundary",
            "TEST-006": "negative",
        }[identifier]
        tests.append(
            {
                "id": identifier,
                "title": title,
                "level": level,
                "category": category,
                "module_ids": ["MOD-001"],
                "requirement_ids": ["REQ-001"],
                "procedure": "执行 " + identifier,
                "expected": "结果符合验收准则",
                "actual": "结果符合验收准则",
                "result": "passed",
                "executed_at": FIXED_TIME,
                "evidence_ids": [evidence[key]],
                "defects": [],
            }
        )
    return {
        "schema_version": 1,
        "environment": {
            "os": "Linux",
            "compiler": "gcc 12.2",
            "container": "none",
            "source_revision": "abc1234",
        },
        "tests": tests,
        "regression": {
            "baseline": "1.0.0",
            "result": "passed",
            "evidence_ids": [evidence["regression"]],
        },
        "open_items": [],
    }


def _vv_report(evidence: Dict[str, str]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "independence": {
            "developer_organizations": ["示例开发组织"],
            "vv_executor": {
                "name": "李四",
                "role": "独立验证执行者",
                "organization": "示例 V&V 组织",
                "independent": True,
            },
            "reviewer": {
                "name": "王五",
                "role": "独立审核者",
                "organization": "示例审核组织",
                "independent": True,
            },
        },
        "activities": [
            {
                "id": "VV-001",
                "type": "code_verification",
                "title": "代码验证",
                "requirement_ids": ["REQ-001"],
                "test_ids": ["TEST-001"],
                "method": "制造解方法",
                "acceptance": "观测阶数不低于 1.8",
                "observed": "观测阶数 1.98",
                "uncertainty": "离散误差主导",
                "result": "passed",
                "evidence_ids": [evidence["code_verification"]],
                "deviations": [],
                "limitations": [],
                "reference_solution": "制造解 T(x)=sin(pi x)",
                "benchmark_source": "",
                "applicability_domain": "",
                "error_metrics": [],
                "trends": [],
                "convergence_study": "",
                "observed_order": "",
            },
            {
                "id": "VV-002",
                "type": "solution_verification",
                "title": "解的验证",
                "requirement_ids": ["REQ-001"],
                "test_ids": ["TEST-002"],
                "method": "网格收敛研究",
                "acceptance": "观测阶数不低于 1.8",
                "observed": "观测阶数 1.96",
                "uncertainty": "网格收敛指数 0.02",
                "result": "passed",
                "evidence_ids": [evidence["solution_verification"]],
                "deviations": [],
                "limitations": [],
                "reference_solution": "",
                "benchmark_source": "",
                "applicability_domain": "",
                "error_metrics": [],
                "trends": [],
                "convergence_study": "三套网格加密",
                "observed_order": "1.96",
            },
            {
                "id": "VV-003",
                "type": "validation",
                "title": "确认",
                "requirement_ids": ["REQ-001"],
                "test_ids": ["TEST-003"],
                "method": "基准题对比",
                "acceptance": "最大相对误差不超过 2%",
                "observed": "最大相对误差 1.2%",
                "uncertainty": "基准题不确定度 0.5%",
                "result": "passed",
                "evidence_ids": [evidence["validation"]],
                "deviations": [],
                "limitations": ["仅覆盖稳态工况"],
                "reference_solution": "",
                "benchmark_source": "示例基准题集 2026",
                "applicability_domain": "稳态一维导热",
                "error_metrics": ["最大相对误差 1.2%"],
                "trends": ["误差随网格加密单调下降"],
                "convergence_study": "",
                "observed_order": "",
            },
        ],
        "conclusions": {
            "overall": "在本适用范围内满足验收准则",
            "limitations": ["未覆盖瞬态工况"],
            "residual_risk": "低",
        },
        "open_items": [],
    }


def _release_artifact(evidence: Dict[str, str]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "release_id": "REL-001",
        "version": "1.0.0",
        "release_scope": ["src", "release"],
        "source_revision": "abc1234",
        "configuration": {
            "compiler": "gcc 12.2",
            "os": "Linux",
            "mpi": "none",
            "dependencies": ["python3"],
            "container_images": [],
        },
        "sbom": {
            "format": "spdx-json",
            "path": "release/sbom.json",
            "evidence_id": evidence["sbom"],
        },
        "reproducibility": {
            "instructions": "两次重建并比对产物哈希",
            "verified": True,
            "evidence_ids": [evidence["reproducibility"]],
        },
        "rollback": {
            "procedure": "恢复上一基线并重跑回归测试",
            "verified": True,
            "evidence_ids": [evidence["rollback"]],
        },
        "known_limitations": ["未覆盖瞬态工况"],
        "open_items": [],
    }


def _traceability() -> Dict[str, Any]:
    nodes = [
        {"id": "REQ-001", "kind": "requirement", "title": "质量守恒"},
        {"id": "DES-001", "kind": "design", "title": "守恒离散"},
        {"id": "MOD-001", "kind": "module", "title": "求解器模块"},
        {"id": "REL-001", "kind": "release", "title": "1.0.0 发布"},
    ]
    for index in range(1, 7):
        nodes.append({"id": "TEST-%03d" % index, "kind": "test", "title": "测试 %d" % index})
    for index in range(1, 4):
        nodes.append({"id": "VV-%03d" % index, "kind": "vv", "title": "V&V 活动 %d" % index})

    links = [
        {"from": "REQ-001", "to": "DES-001", "relation": "allocated_to"},
        {"from": "DES-001", "to": "MOD-001", "relation": "implemented_by"},
        {"from": "REL-001", "to": "REQ-001", "relation": "contains"},
        {"from": "REL-001", "to": "MOD-001", "relation": "contains"},
    ]
    for index in range(1, 7):
        test_id = "TEST-%03d" % index
        links.append({"from": test_id, "to": "MOD-001", "relation": "exercises"})
        links.append({"from": test_id, "to": "REQ-001", "relation": "verifies"})
    for index in range(1, 4):
        vv_id = "VV-%03d" % index
        links.append({"from": vv_id, "to": "REQ-001", "relation": "validates"})
        links.append({"from": vv_id, "to": "TEST-%03d" % index, "relation": "uses"})
    return {"schema_version": 1, "nodes": nodes, "links": links}


def approve_stage(
    root: Path,
    stage: str,
    approver_name: str = "独立审核人",
    organization: str = "示例 QA 组织",
) -> Path:
    relative = STAGE_ARTIFACTS[stage]
    artifact_file = root / ".nuclear-dev" / relative
    approval = {
        "stage": stage,
        "approver": {
            "name": approver_name,
            "role": "阶段批准人",
            "organization": organization,
            "actor_type": "human",
            "credential": "CERT-001",
        },
        "decision": "approved",
        "date": FIXED_TIME,
        "scope": [relative],
        "artifact_sha256": {relative: sha256_file(artifact_file)},
        "statement": "本阶段产物经独立审查后批准。",
    }
    return write_json(root / ".nuclear-dev" / "approvals" / (stage + ".json"), approval)


def build_valid_project(root: Path) -> Dict[str, str]:
    """在 root 下构造一个七阶段全部可通门的项目，返回证据 ID 映射。

    夹具直接调用冻结内核，避免为每条测试重复启动十几次子进程；
    CLI 自身的行为在 test_cli.py 中单独覆盖。
    """
    nuclearlib.init_project(root, name="示例核能软件", project_id="example-nuclear")

    write_text(root / "src" / "solver.py", "def solve():\n    return 0.0\n")
    write_text(root / "release" / "notes.txt", "示例发布说明\n")
    write_json(root / "release" / "sbom.json", {"spdxVersion": "SPDX-2.3", "name": "example-nuclear"})

    evidence: Dict[str, str] = {}
    for index, (key, relative, kind) in enumerate(EVIDENCE_FILES, 1):
        path = write_text(root / relative, "evidence %d: %s\n" % (index, kind))
        record = with_write_retry(
            lambda: nuclearlib.add_evidence(
                root,
                source=relative,
                kind=kind,
                producer="示例测试夹具",
                command="fixture",
                result="passed",
                captured_at=FIXED_TIME,
            )
        )
        evidence[key] = record["id"]

    artifacts = {
        "plan": _plan_artifact(),
        "requirements": _requirements_artifact(),
        "design": _design_artifact(),
        "implementation": _implementation_artifact(evidence),
        "test": _test_report(evidence),
        "vv": _vv_report(evidence),
        "release": _release_artifact(evidence),
    }
    for stage in STAGES:
        write_json(root / ".nuclear-dev" / STAGE_ARTIFACTS[stage], artifacts[stage])
    write_json(root / ".nuclear-dev" / "traceability.json", _traceability())
    for stage in STAGES:
        approve_stage(root, stage, organization="示例 V&V 批准组织")
    return evidence


def mutate_json(path: Path, mutator) -> Any:
    value = read_json(path)
    mutator(value)
    write_json(path, value)
    return value


class ProjectCase:
    """为测试类提供临时项目与有效夹具。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def artifact_path(self, stage: str) -> Path:
        return self.root / ".nuclear-dev" / STAGE_ARTIFACTS[stage]


class McpClient:
    """以 stdio 直接驱动 nuclearmcp.py 的测试客户端。"""

    def __init__(
        self,
        workspaces: List[Path],
        allow_write: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        argv = [sys.executable, str(MCP)]
        for workspace in workspaces:
            argv += ["--workspace", str(workspace)]
        if allow_write:
            argv.append("--allow-write")
        argv += list(extra_args or [])
        self.process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env(),
        )
        self._next_id = 0

    def send(self, message: Dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def read(self) -> Dict[str, Any]:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            stderr = b""
            if self.process.stderr is not None:
                stderr = self.process.stderr.read()
            raise AssertionError("服务端未返回消息: " + stderr.decode("utf-8", "replace"))
        return json.loads(line.decode("utf-8"))

    def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next_id += 1
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.read()

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def initialize(self) -> Dict[str, Any]:
        response = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tests", "version": "1.0"},
            },
        )
        self.notify("notifications/initialized")
        return response

    def call(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def payload(self, name: str, arguments: Optional[Dict[str, Any]] = None):
        response = self.call(name, arguments)
        if "error" in response:
            return response["error"], True
        result = response.get("result", {})
        content = result.get("content") or []
        if not content:
            raise AssertionError("工具结果缺少 content: %s" % response)
        return json.loads(content[0]["text"]), bool(result.get("isError"))

    def close(self) -> None:
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
