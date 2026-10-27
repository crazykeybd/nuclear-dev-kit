#!/usr/bin/env python3
"""确定性的工作区、追溯、证据、门禁与清单工具。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

KIT_VERSION = "0.1.0"
SCHEMA_VERSION = 1
STAGES = ["plan", "requirements", "design", "implementation", "test", "vv", "release"]
STAGE_LABELS = {
    "plan": "软件策划",
    "requirements": "需求分析",
    "design": "软件设计",
    "implementation": "编码实现",
    "test": "软件测试",
    "vv": "软件验证与确认",
    "release": "软件发布",
}
STAGE_ARTIFACTS = {
    "plan": "stages/plan/plan.json",
    "requirements": "stages/requirements/requirements.json",
    "design": "stages/design/design.json",
    "implementation": "stages/implementation/implementation.json",
    "test": "stages/test/test-report.json",
    "vv": "stages/vv/vv-report.json",
    "release": "stages/release/release.json",
}
STAGE_SKILLS = {
    "plan": "nuclear-plan",
    "requirements": "nuclear-requirements",
    "design": "nuclear-design",
    "implementation": "nuclear-implementation",
    "test": "nuclear-test",
    "vv": "nuclear-vv",
    "release": "nuclear-release",
}
TRACE_KIND = {
    "plan": None,
    "requirements": "requirement",
    "design": "design",
    "implementation": "module",
    "test": "test",
    "vv": "vv",
    "release": "release",
}
ID_PREFIX = {
    "requirement": "REQ",
    "design": "DES",
    "module": "MOD",
    "test": "TEST",
    "vv": "VV",
    "release": "REL",
}
ID_RE = {
    "requirement": r"^REQ-[0-9]{3,}$",
    "design": r"^DES-[0-9]{3,}$",
    "module": r"^MOD-[0-9]{3,}$",
    "test": r"^TEST-[0-9]{3,}$",
    "vv": r"^VV-[0-9]{3,}$",
    "release": r"^REL-[0-9]{3,}$",
}
ALLOWED_LINKS = {
    ("requirement", "design", "allocated_to"),
    ("design", "module", "implemented_by"),
    ("test", "module", "exercises"),
    ("test", "requirement", "verifies"),
    ("vv", "requirement", "validates"),
    ("vv", "test", "uses"),
    ("release", "requirement", "contains"),
    ("release", "module", "contains"),
}
PLACEHOLDERS = {"TBD", "TODO", "UNRESOLVED", "PENDING", "NOT RECORDED", "UNKNOWN", "DRAFT", "IN PROGRESS"}


class NuclearError(Exception):
    """可向用户展示且带有可执行指引的失败。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        raise NuclearError("文件不存在: %s" % path)
    except json.JSONDecodeError as exc:
        raise NuclearError("JSON 无效: %s: %s" % (path, exc))


def root_path(root: str) -> Path:
    return Path(root).expanduser().resolve()


def state_path(root: Path) -> Path:
    return root / ".nuclear-dev"


def stage_path(root: Path, stage: str) -> Path:
    return state_path(root) / STAGE_ARTIFACTS[stage]


def approval_path(root: Path, stage: str) -> Path:
    return state_path(root) / "approvals" / (stage + ".json")


def is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def project_metadata(root: Path) -> Dict[str, Any]:
    return load_json(state_path(root) / "project.json")


def init_project(root: Path, name: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    state = state_path(root)
    project_file = state / "project.json"
    if project_file.exists():
        raise NuclearError("工作区已初始化: %s" % project_file)
    display_name = (name or root.name or "nuclear-software").strip()
    if not display_name:
        raise NuclearError("项目名不能为空")
    identifier = (project_id or re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-") or "nuclear-software")
    project = {
        "schema_version": SCHEMA_VERSION,
        "project_id": identifier,
        "name": display_name,
        "created_at": utc_now(),
        "kit_version": KIT_VERSION,
        "safety_classification": "pending",
        "vv_level": "pending",
    }
    traceability = {"schema_version": SCHEMA_VERSION, "nodes": [], "links": []}
    evidence = {"schema_version": SCHEMA_VERSION, "evidence": []}
    state.mkdir(parents=True, exist_ok=True)
    for stage in STAGES:
        stage_path(root, stage).parent.mkdir(parents=True, exist_ok=True)
    (state / "evidence").mkdir(parents=True, exist_ok=True)
    (state / "approvals").mkdir(parents=True, exist_ok=True)
    (state / "manifests").mkdir(parents=True, exist_ok=True)
    atomic_write_json(project_file, project)
    atomic_write_json(state / "traceability.json", traceability)
    atomic_write_json(state / "evidence" / "index.json", evidence)
    return project


# --- 小型 schema 校验器 -------------------------------------------------

def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
    }.get(expected, False)


def _iso_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _add(errors: List[str], path: str, message: str) -> None:
    errors.append("%s: %s" % (path, message))


def validate_schema(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    expected = schema.get("type")
    if expected and not _matches_type(value, expected):
        _add(errors, path, "应为 %s，实际为 %s" % (expected, _type_name(value)))
        return
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                _add(errors, path, "缺少字段 %s" % key)
        properties = schema.get("properties", {})
        for key, child_schema in properties.items():
            if key in value:
                validate_schema(value[key], child_schema, "%s.%s" % (path, key), errors)
        values_schema = schema.get("values")
        if values_schema is not None:
            for key, child in value.items():
                validate_schema(child, values_schema, "%s.%s" % (path, key), errors)
    elif expected == "array":
        minimum = schema.get("min_items")
        if minimum is not None and len(value) < minimum:
            _add(errors, path, "至少需要 %d 项" % minimum)
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, child in enumerate(value):
                validate_schema(child, item_schema, "%s[%d]" % (path, index), errors)
    elif expected == "string":
        if schema.get("nonempty") and not value.strip():
            _add(errors, path, "不能为空")
        if "enum" in schema and value not in schema["enum"]:
            _add(errors, path, "必须为 %s 之一" % ", ".join(str(item) for item in schema["enum"]))
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, value):
            _add(errors, path, "不匹配格式 %s" % pattern)
        if schema.get("format") == "date-time" and not _iso_datetime(value):
            _add(errors, path, "必须是 ISO-8601 日期时间")
    elif expected == "integer":
        if "const" in schema and value != schema["const"]:
            _add(errors, path, "必须为 %s" % schema["const"])


def _string(nonempty: bool = True, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"type": "string"}
    if nonempty:
        result["nonempty"] = True
    result.update(extra)
    return result


def _boolean() -> Dict[str, Any]:
    return {"type": "boolean"}


def _array(items: Dict[str, Any], minimum: int = 0) -> Dict[str, Any]:
    return {"type": "array", "items": items, "min_items": minimum}


def _object(required: Sequence[str], properties: Dict[str, Any], values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"type": "object", "required": list(required), "properties": properties}
    if values is not None:
        result["values"] = values
    return result


OPEN_ITEM = _object(
    ["id", "description", "status", "owner"],
    {
        "id": _string(pattern=r"^OI-[0-9]{3,}$"),
        "description": _string(),
        "status": _string(enum=["open", "closed", "accepted"]),
        "owner": _string(),
        "due": _string(nonempty=False),
    },
)

PROJECT_SCHEMA = _object(
    ["schema_version", "project_id", "name", "created_at", "kit_version", "safety_classification", "vv_level"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "project_id": _string(pattern=r"^[a-z0-9][a-z0-9-]*$"),
        "name": _string(),
        "created_at": _string(format="date-time"),
        "kit_version": _string(),
        "safety_classification": _string(),
        "vv_level": _string(),
    },
)

NODE_SCHEMA = _object(
    ["id", "kind", "title"],
    {
        "id": _string(),
        "kind": _string(enum=list(ID_PREFIX.keys())),
        "title": _string(),
    },
)

TRACEABILITY_SCHEMA = _object(
    ["schema_version", "nodes", "links"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "nodes": _array(NODE_SCHEMA),
        "links": _array(
            _object(
                ["from", "to", "relation"],
                {"from": _string(), "to": _string(), "relation": _string()},
            )
        ),
    },
)

EVIDENCE_RECORD_SCHEMA = _object(
    ["id", "kind", "path", "sha256", "captured_at", "producer", "command", "result"],
    {
        "id": _string(pattern=r"^EVID-[0-9]{3,}$"),
        "kind": _string(),
        "path": _string(),
        "sha256": _string(pattern=r"^[0-9a-f]{64}$"),
        "captured_at": _string(format="date-time"),
        "producer": _string(),
        "command": _string(),
        "result": _string(enum=["passed", "failed", "observed", "not_applicable"]),
    },
)

EVIDENCE_INDEX_SCHEMA = _object(
    ["schema_version", "evidence"],
    {"schema_version": {"type": "integer", "const": SCHEMA_VERSION}, "evidence": _array(EVIDENCE_RECORD_SCHEMA)},
)

APPROVER_SCHEMA = _object(
    ["name", "role", "organization", "actor_type"],
    {
        "name": _string(),
        "role": _string(),
        "organization": _string(),
        "actor_type": _string(enum=["human"]),
        "credential": _string(nonempty=False),
    },
)

APPROVAL_SCHEMA = _object(
    ["stage", "approver", "decision", "date", "scope", "artifact_sha256", "statement"],
    {
        "stage": _string(enum=STAGES),
        "approver": APPROVER_SCHEMA,
        "decision": _string(enum=["approved", "rejected"]),
        "date": _string(format="date-time"),
        "scope": _array(_string(), 1),
        "artifact_sha256": {"type": "object", "values": _string(pattern=r"^[0-9a-f]{64}$")},
        "statement": _string(),
        "signature": _string(nonempty=False),
    },
)

PLAN_SCHEMA = _object(
    ["schema_version", "project", "standards", "vv_strategy", "tool_qualification", "personnel", "configuration_management", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "project": _object(
            ["name", "purpose", "safety_classification", "classification_basis", "vv_level", "vv_basis"],
            {
                "name": _string(),
                "purpose": _string(),
                "safety_classification": _string(),
                "classification_basis": _string(),
                "vv_level": _string(),
                "vv_basis": _string(),
            },
        ),
        "standards": _array(
            _object(
                ["id", "title", "revision", "applicability", "status", "source"],
                {
                    "id": _string(),
                    "title": _string(),
                    "revision": _string(),
                    "applicability": _string(),
                    "status": _string(enum=["applicable", "not_applicable", "pending"]),
                    "source": _string(),
                },
            ),
            1,
        ),
        "vv_strategy": _object(
            ["levels", "independence_required", "verification_methods", "validation_strategy"],
            {
                "levels": _array(_string(), 1),
                "independence_required": _boolean(),
                "verification_methods": _array(_string(), 1),
                "validation_strategy": _string(),
            },
        ),
        "tool_qualification": _array(
            _object(
                ["tool", "version", "role", "qualification_status", "basis", "limitations"],
                {
                    "tool": _string(),
                    "version": _string(),
                    "role": _string(),
                    "qualification_status": _string(enum=["qualified", "not_required", "pending"]),
                    "basis": _string(),
                    "limitations": _string(),
                },
            ),
            1,
        ),
        "personnel": _array(
            _object(
                ["role", "required_qualification", "assigned_person", "evidence", "status"],
                {
                    "role": _string(),
                    "required_qualification": _string(),
                    "assigned_person": _string(),
                    "evidence": _string(),
                    "status": _string(enum=["qualified", "pending"]),
                },
            ),
            1,
        ),
        "configuration_management": _object(
            ["vcs", "baseline", "change_control", "backup"],
            {"vcs": _string(), "baseline": _string(), "change_control": _string(), "backup": _string()},
        ),
        "open_items": _array(OPEN_ITEM),
    },
)

ACCEPTANCE_SCHEMA = _object(
    ["id", "criterion", "method", "tolerance", "evidence_kind"],
    {"id": _string(), "criterion": _string(), "method": _string(), "tolerance": _string(), "evidence_kind": _string()},
)

REQUIREMENT_SCHEMA = _object(
    ["id", "title", "statement", "rationale", "source", "priority", "safety_class", "category", "verification_method", "validation_required", "acceptance_criteria", "status"],
    {
        "id": _string(pattern=ID_RE["requirement"]),
        "title": _string(),
        "statement": _string(),
        "rationale": _string(),
        "source": _string(),
        "priority": _string(enum=["critical", "high", "medium", "low"]),
        "safety_class": _string(),
        "category": _string(),
        "verification_method": _string(enum=["test", "analysis", "inspection", "demonstration"]),
        "validation_required": _boolean(),
        "acceptance_criteria": _array(ACCEPTANCE_SCHEMA, 1),
        "status": _string(enum=["defined", "approved"]),
        "interfaces": _array(_string(nonempty=False)),
    },
)

REQUIREMENTS_SCHEMA = _object(
    ["schema_version", "scope", "requirements", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "scope": _object(
            ["description", "applicability", "exclusions", "assumptions", "limitations"],
            {
                "description": _string(),
                "applicability": _string(),
                "exclusions": _array(_string()),
                "assumptions": _array(_string()),
                "limitations": _array(_string()),
            },
        ),
        "requirements": _array(REQUIREMENT_SCHEMA, 1),
        "open_items": _array(OPEN_ITEM),
    },
)

DESIGN_ITEM_SCHEMA = _object(
    ["id", "title", "requirements", "description", "algorithm", "data_structures", "interfaces", "error_control", "verification_plan", "status"],
    {
        "id": _string(pattern=ID_RE["design"]),
        "title": _string(),
        "requirements": _array(_string(pattern=ID_RE["requirement"]), 1),
        "description": _string(),
        "algorithm": _string(),
        "data_structures": _string(),
        "interfaces": _array(_string()),
        "error_control": _string(),
        "verification_plan": _string(),
        "status": _string(enum=["designed", "approved"]),
    },
)

DESIGN_SCHEMA = _object(
    ["schema_version", "architecture", "models", "design_items", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "architecture": _object(
            ["overview", "components"],
            {
                "overview": _string(),
                "components": _array(
                    _object(
                        ["id", "name", "responsibility", "interfaces"],
                        {"id": _string(), "name": _string(), "responsibility": _string(), "interfaces": _array(_string())},
                    ),
                    1,
                ),
            },
        ),
        "models": _array(
            _object(
                ["id", "name", "equations", "assumptions", "applicability", "discretization", "stability", "conservation", "error_analysis"],
                {
                    "id": _string(),
                    "name": _string(),
                    "equations": _array(_string(), 1),
                    "assumptions": _array(_string()),
                    "applicability": _string(),
                    "discretization": _string(),
                    "stability": _string(),
                    "conservation": _string(),
                    "error_analysis": _string(),
                },
            ),
            1,
        ),
        "design_items": _array(DESIGN_ITEM_SCHEMA, 1),
        "open_items": _array(OPEN_ITEM),
    },
)

MODULE_SCHEMA = _object(
    ["id", "title", "design_ids", "paths", "language", "entrypoints", "unit_tests", "static_analysis", "status"],
    {
        "id": _string(pattern=ID_RE["module"]),
        "title": _string(),
        "design_ids": _array(_string(pattern=ID_RE["design"]), 1),
        "paths": _array(_string(), 1),
        "language": _string(),
        "entrypoints": _array(_string(), 1),
        "unit_tests": _array(_string()),
        "static_analysis": _string(),
        "status": _string(enum=["implemented", "approved"]),
    },
)

IMPLEMENTATION_SCHEMA = _object(
    ["schema_version", "source_control", "build", "modules", "build_evidence_ids", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "source_control": _object(
            ["repository", "revision", "branch", "dirty"],
            {"repository": _string(), "revision": _string(), "branch": _string(), "dirty": _boolean()},
        ),
        "build": _object(
            ["system", "compiler", "compiler_version", "flags", "dependencies", "mpi", "os", "container"],
            {
                "system": _string(),
                "compiler": _string(),
                "compiler_version": _string(),
                "flags": _array(_string()),
                "dependencies": _array(_string()),
                "mpi": _string(),
                "os": _string(),
                "container": _string(),
            },
        ),
        "modules": _array(MODULE_SCHEMA, 1),
        "build_evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1),
        "open_items": _array(OPEN_ITEM),
    },
)

TEST_SCHEMA = _object(
    ["id", "title", "level", "category", "module_ids", "requirement_ids", "procedure", "expected", "actual", "result", "executed_at", "evidence_ids", "defects"],
    {
        "id": _string(pattern=ID_RE["test"]),
        "title": _string(),
        "level": _string(enum=["unit", "model", "system"]),
        "category": _string(enum=["unit", "model", "system", "conservation", "boundary", "negative", "regression"]),
        "module_ids": _array(_string(pattern=ID_RE["module"]), 1),
        "requirement_ids": _array(_string(pattern=ID_RE["requirement"]), 1),
        "procedure": _string(),
        "expected": _string(),
        "actual": _string(),
        "result": _string(enum=["passed", "failed", "not_run"]),
        "executed_at": _string(format="date-time"),
        "evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1),
        "defects": _array(_string()),
    },
)

TEST_REPORT_SCHEMA = _object(
    ["schema_version", "environment", "tests", "regression", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "environment": _object(
            ["os", "compiler", "container", "source_revision"],
            {"os": _string(), "compiler": _string(), "container": _string(), "source_revision": _string()},
        ),
        "tests": _array(TEST_SCHEMA, 1),
        "regression": _object(
            ["baseline", "result", "evidence_ids"],
            {
                "baseline": _string(),
                "result": _string(enum=["passed", "failed", "not_run"]),
                "evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1),
            },
        ),
        "open_items": _array(OPEN_ITEM),
    },
)

VV_ACTIVITY_SCHEMA = _object(
    ["id", "type", "title", "requirement_ids", "test_ids", "method", "acceptance", "observed", "uncertainty", "result", "evidence_ids", "deviations", "limitations"],
    {
        "id": _string(pattern=ID_RE["vv"]),
        "type": _string(enum=["code_verification", "solution_verification", "validation"]),
        "title": _string(),
        "requirement_ids": _array(_string(pattern=ID_RE["requirement"])),
        "test_ids": _array(_string(pattern=ID_RE["test"])),
        "method": _string(),
        "acceptance": _string(),
        "observed": _string(),
        "uncertainty": _string(),
        "result": _string(enum=["passed", "failed", "not_run"]),
        "evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1),
        "deviations": _array(_string()),
        "limitations": _array(_string()),
        "benchmark_source": _string(nonempty=False),
        "applicability_domain": _string(nonempty=False),
        "error_metrics": _array(_string()),
        "trends": _array(_string()),
        "reference_solution": _string(nonempty=False),
        "convergence_study": _string(nonempty=False),
        "observed_order": _string(nonempty=False),
    },
)

VV_SCHEMA = _object(
    ["schema_version", "independence", "activities", "conclusions", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "independence": _object(
            ["developer_organizations", "vv_executor", "reviewer"],
            {
                "developer_organizations": _array(_string(), 1),
                "vv_executor": _object(
                    ["name", "role", "organization", "independent"],
                    {"name": _string(), "role": _string(), "organization": _string(), "independent": _boolean()},
                ),
                "reviewer": _object(
                    ["name", "role", "organization", "independent"],
                    {"name": _string(), "role": _string(), "organization": _string(), "independent": _boolean()},
                ),
            },
        ),
        "activities": _array(VV_ACTIVITY_SCHEMA, 1),
        "conclusions": _object(
            ["overall", "limitations", "residual_risk"],
            {"overall": _string(), "limitations": _array(_string()), "residual_risk": _string()},
        ),
        "open_items": _array(OPEN_ITEM),
    },
)

RELEASE_SCHEMA = _object(
    ["schema_version", "release_id", "version", "release_scope", "source_revision", "configuration", "sbom", "reproducibility", "rollback", "known_limitations", "open_items"],
    {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "release_id": _string(pattern=ID_RE["release"]),
        "version": _string(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.-]+)?$"),
        "release_scope": _array(_string(), 1),
        "source_revision": _string(),
        "configuration": _object(
            ["compiler", "os", "mpi", "dependencies", "container_images"],
            {
                "compiler": _string(),
                "os": _string(),
                "mpi": _string(),
                "dependencies": _array(_string()),
                "container_images": _array(_string()),
            },
        ),
        "sbom": _object(
            ["format", "path", "evidence_id"],
            {"format": _string(), "path": _string(), "evidence_id": _string(pattern=r"^EVID-[0-9]{3,}$")},
        ),
        "reproducibility": _object(
            ["instructions", "verified", "evidence_ids"],
            {"instructions": _string(), "verified": _boolean(), "evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1)},
        ),
        "rollback": _object(
            ["procedure", "verified", "evidence_ids"],
            {"procedure": _string(), "verified": _boolean(), "evidence_ids": _array(_string(pattern=r"^EVID-[0-9]{3,}$"), 1)},
        ),
        "known_limitations": _array(_string()),
        "open_items": _array(OPEN_ITEM),
    },
)

STAGE_SCHEMAS = {
    "plan": PLAN_SCHEMA,
    "requirements": REQUIREMENTS_SCHEMA,
    "design": DESIGN_SCHEMA,
    "implementation": IMPLEMENTATION_SCHEMA,
    "test": TEST_REPORT_SCHEMA,
    "vv": VV_SCHEMA,
    "release": RELEASE_SCHEMA,
}


def find_placeholders(value: Any, path: str = "$") -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_placeholders(child, "%s.%s" % (path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_placeholders(child, "%s[%d]" % (path, index)))
    elif isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in PLACEHOLDERS or normalized.startswith("TBD:"):
            found.append("%s: 未完成占位值 %s" % (path, value))
    return found


def open_item_errors(value: Any, path: str = "$") -> List[str]:
    errors: List[str] = []
    if isinstance(value, dict):
        if "open_items" in value and isinstance(value["open_items"], list):
            for index, item in enumerate(value["open_items"]):
                if isinstance(item, dict) and item.get("status") != "closed":
                    errors.append("%s.open_items[%d]: 未关闭事项 %s" % (path, index, item.get("id", "?")))
        for key, child in value.items():
            if key != "open_items":
                errors.extend(open_item_errors(child, "%s.%s" % (path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(open_item_errors(child, "%s[%d]" % (path, index)))
    return errors


def validate_artifact(stage: str, artifact: Any) -> List[str]:
    errors: List[str] = []
    if stage not in STAGE_SCHEMAS:
        return ["未知阶段: %s" % stage]
    validate_schema(artifact, STAGE_SCHEMAS[stage], stage, errors)
    errors.extend(find_placeholders(artifact, stage))
    errors.extend(open_item_errors(artifact, stage))
    return errors


def validate_project(root: Path) -> List[str]:
    errors: List[str] = []
    state = state_path(root)
    project_file = state / "project.json"
    if not project_file.exists():
        return ["未初始化: 缺少 %s；先运行 nuclearctl.py init" % project_file]
    project = load_json(project_file)
    validate_schema(project, PROJECT_SCHEMA, "project", errors)
    trace_file = state / "traceability.json"
    if not trace_file.exists():
        errors.append("缺少 traceability.json")
    else:
        validate_traceability(root, load_json(trace_file), errors)
    evidence_file = state / "evidence" / "index.json"
    if not evidence_file.exists():
        errors.append("缺少 evidence/index.json")
    else:
        validate_evidence(root, load_json(evidence_file), errors)
    for stage in STAGES:
        path = stage_path(root, stage)
        if path.exists():
            try:
                artifact = load_json(path)
            except NuclearError as exc:
                errors.append(str(exc))
                continue
            errors.extend("%s: %s" % (STAGE_ARTIFACTS[stage], item) for item in validate_artifact(stage, artifact))
        approval = approval_path(root, stage)
        if approval.exists():
            errors.extend(validate_approval(root, stage, errors_only=True))
    return errors


def validate_traceability(root: Path, trace: Any, errors: List[str]) -> None:
    validate_schema(trace, TRACEABILITY_SCHEMA, "traceability", errors)
    if not isinstance(trace, dict):
        return
    nodes = trace.get("nodes", [])
    links = trace.get("links", [])
    if not isinstance(nodes, list) or not isinstance(links, list):
        return
    by_id: Dict[str, Dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        identifier = node.get("id")
        kind = node.get("kind")
        if not isinstance(identifier, str) or not isinstance(kind, str):
            continue
        if identifier in by_id:
            _add(errors, "traceability.nodes[%d]" % index, "重复节点 ID %s" % identifier)
        by_id[identifier] = node
        pattern = ID_RE.get(kind)
        if pattern and not re.match(pattern, identifier):
            _add(errors, "traceability.nodes[%d].id" % index, "%s 的 ID 格式无效" % kind)
        expected_prefix = ID_PREFIX.get(kind)
        if expected_prefix and not identifier.startswith(expected_prefix + "-"):
            _add(errors, "traceability.nodes[%d].id" % index, "ID 前缀应为 %s-" % expected_prefix)
    seen_links = set()
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            continue
        source_id = link.get("from")
        target_id = link.get("to")
        relation = link.get("relation")
        key = (source_id, target_id, relation)
        if key in seen_links:
            _add(errors, "traceability.links[%d]" % index, "重复关系")
        seen_links.add(key)
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if source is None:
            _add(errors, "traceability.links[%d].from" % index, "未声明节点 %s" % source_id)
        if target is None:
            _add(errors, "traceability.links[%d].to" % index, "未声明节点 %s" % target_id)
        if source is not None and target is not None:
            triple = (source.get("kind"), target.get("kind"), relation)
            if triple not in ALLOWED_LINKS:
                _add(errors, "traceability.links[%d]" % index, "不允许的关系 %s --%s--> %s" % (source.get("kind"), relation, target.get("kind")))


def validate_evidence(root: Path, index: Any, errors: List[str]) -> None:
    validate_schema(index, EVIDENCE_INDEX_SCHEMA, "evidence.index", errors)
    if not isinstance(index, dict) or not isinstance(index.get("evidence"), list):
        return
    seen = set()
    for position, record in enumerate(index["evidence"]):
        if not isinstance(record, dict):
            continue
        identifier = record.get("id")
        if identifier in seen:
            _add(errors, "evidence[%d]" % position, "重复证据 ID %s" % identifier)
        seen.add(identifier)
        relative = record.get("path")
        if not isinstance(relative, str):
            continue
        candidate = (root / relative).resolve()
        if not is_within(root, candidate):
            _add(errors, "evidence[%d].path" % position, "证据必须位于项目目录内")
            continue
        if not candidate.is_file():
            _add(errors, "evidence[%d].path" % position, "证据文件不存在: %s" % relative)
            continue
        actual = sha256_file(candidate)
        if actual != record.get("sha256"):
            _add(errors, "evidence[%d].sha256" % position, "SHA256 不匹配: %s" % relative)


def validate_approval(root: Path, stage: str, errors_only: bool = False) -> List[str]:
    errors: List[str] = []
    path = approval_path(root, stage)
    if not path.exists():
        return ["缺少人工批准记录: %s" % path.relative_to(state_path(root)).as_posix()]
    try:
        approval = load_json(path)
    except NuclearError as exc:
        return [str(exc)]
    validate_schema(approval, APPROVAL_SCHEMA, "approval.%s" % stage, errors)
    if not isinstance(approval, dict):
        return errors
    if approval.get("stage") != stage:
        _add(errors, "approval.stage", "阶段必须为 %s" % stage)
    if approval.get("decision") != "approved":
        _add(errors, "approval.decision", "决策不是 approved")
    scope = approval.get("scope", [])
    hashes = approval.get("artifact_sha256", {})
    if isinstance(scope, list) and isinstance(hashes, dict):
        for relative in scope:
            if not isinstance(relative, str):
                continue
            if relative not in hashes:
                _add(errors, "approval.artifact_sha256", "scope 中 %s 缺少 SHA256" % relative)
        artifact_relative = STAGE_ARTIFACTS[stage]
        if artifact_relative not in scope:
            _add(errors, "approval.scope", "必须包含当前阶段产物 %s" % artifact_relative)
        for relative, expected in hashes.items():
            if not isinstance(relative, str) or not isinstance(expected, str):
                continue
            candidate = (root / ".nuclear-dev" / relative).resolve()
            if not is_within(state_path(root), candidate):
                _add(errors, "approval.artifact_sha256.%s" % relative, "路径必须位于 .nuclear-dev 内")
                continue
            if not candidate.is_file():
                _add(errors, "approval.artifact_sha256.%s" % relative, "被批准文件不存在")
                continue
            if sha256_file(candidate) != expected:
                _add(errors, "approval.artifact_sha256.%s" % relative, "产物已变化，批准失效")
    return errors


# --- 跨阶段校验 -------------------------------------------------

def artifact_ids(stage: str, artifact: Dict[str, Any]) -> List[str]:
    if stage == "requirements":
        return [item["id"] for item in artifact.get("requirements", [])]
    if stage == "design":
        return [item["id"] for item in artifact.get("design_items", [])]
    if stage == "implementation":
        return [item["id"] for item in artifact.get("modules", [])]
    if stage == "test":
        return [item["id"] for item in artifact.get("tests", [])]
    if stage == "vv":
        return [item["id"] for item in artifact.get("activities", [])]
    if stage == "release":
        return [artifact.get("release_id")] if artifact.get("release_id") else []
    return []


def _trace_index(trace: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], set]:
    nodes = {}
    for node in trace.get("nodes", []):
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            nodes[node["id"]] = node
    links = set()
    for link in trace.get("links", []):
        if isinstance(link, dict):
            links.add((link.get("from"), link.get("to"), link.get("relation")))
    return nodes, links


def _check_trace_nodes(stage: str, artifact: Dict[str, Any], trace: Dict[str, Any], errors: List[str]) -> None:
    kind = TRACE_KIND[stage]
    if kind is None:
        return
    nodes, _ = _trace_index(trace)
    for identifier in artifact_ids(stage, artifact):
        node = nodes.get(identifier)
        if node is None:
            _add(errors, "traceability", "%s 未登记节点 %s" % (stage, identifier))
        elif node.get("kind") != kind:
            _add(errors, "traceability", "%s 的节点类型应为 %s" % (identifier, kind))


def _check_links(stage: str, artifacts: Dict[str, Dict[str, Any]], trace: Dict[str, Any], errors: List[str]) -> None:
    _, links = _trace_index(trace)
    if stage == "design":
        req_ids = set(artifact_ids("requirements", artifacts["requirements"]))
        design_ids = set(artifact_ids("design", artifacts["design"]))
        for req_id in sorted(req_ids):
            if not any((req_id, design_id, "allocated_to") in links for design_id in design_ids):
                _add(errors, "traceability", "%s 未分配到任何 DES" % req_id)
        for design in artifacts["design"].get("design_items", []):
            for req_id in design.get("requirements", []):
                if (req_id, design.get("id"), "allocated_to") not in links:
                    _add(errors, "traceability", "缺少关系 %s --allocated_to--> %s" % (req_id, design.get("id")))
    elif stage == "implementation":
        design_ids = set(artifact_ids("design", artifacts["design"]))
        module_ids = set(artifact_ids("implementation", artifacts["implementation"]))
        for design_id in sorted(design_ids):
            if not any((design_id, module_id, "implemented_by") in links for module_id in module_ids):
                _add(errors, "traceability", "%s 未映射到任何 MOD" % design_id)
        for module in artifacts["implementation"].get("modules", []):
            for design_id in module.get("design_ids", []):
                if (design_id, module.get("id"), "implemented_by") not in links:
                    _add(errors, "traceability", "缺少关系 %s --implemented_by--> %s" % (design_id, module.get("id")))
    elif stage == "test":
        req_ids = set(artifact_ids("requirements", artifacts["requirements"]))
        module_ids = set(artifact_ids("implementation", artifacts["implementation"]))
        test_ids = set(artifact_ids("test", artifacts["test"]))
        for module_id in sorted(module_ids):
            if not any((test_id, module_id, "exercises") in links for test_id in test_ids):
                _add(errors, "traceability", "%s 没有测试覆盖" % module_id)
        for req_id in sorted(req_ids):
            if not any((test_id, req_id, "verifies") in links for test_id in test_ids):
                _add(errors, "traceability", "%s 没有测试验证" % req_id)
        for test in artifacts["test"].get("tests", []):
            for module_id in test.get("module_ids", []):
                if (test.get("id"), module_id, "exercises") not in links:
                    _add(errors, "traceability", "缺少关系 %s --exercises--> %s" % (test.get("id"), module_id))
            for req_id in test.get("requirement_ids", []):
                if (test.get("id"), req_id, "verifies") not in links:
                    _add(errors, "traceability", "缺少关系 %s --verifies--> %s" % (test.get("id"), req_id))
    elif stage == "vv":
        req_ids = set(artifact_ids("requirements", artifacts["requirements"]))
        test_ids = set(artifact_ids("test", artifacts["test"]))
        vv_ids = set(artifact_ids("vv", artifacts["vv"]))
        requirements = {item["id"]: item for item in artifacts["requirements"].get("requirements", [])}
        for req_id in sorted(req_ids):
            if requirements.get(req_id, {}).get("validation_required") and not any((vv_id, req_id, "validates") in links for vv_id in vv_ids):
                _add(errors, "traceability", "%s 要求确认但没有 V&V 活动" % req_id)
        for activity in artifacts["vv"].get("activities", []):
            for req_id in activity.get("requirement_ids", []):
                if (activity.get("id"), req_id, "validates") not in links:
                    _add(errors, "traceability", "缺少关系 %s --validates--> %s" % (activity.get("id"), req_id))
            for test_id in activity.get("test_ids", []):
                if (activity.get("id"), test_id, "uses") not in links:
                    _add(errors, "traceability", "缺少关系 %s --uses--> %s" % (activity.get("id"), test_id))
    elif stage == "release":
        release_id = artifacts["release"].get("release_id")
        req_ids = set(artifact_ids("requirements", artifacts["requirements"]))
        module_ids = set(artifact_ids("implementation", artifacts["implementation"]))
        for identifier in sorted(req_ids | module_ids):
            if (release_id, identifier, "contains") not in links:
                _add(errors, "traceability", "%s 未纳入发布 %s" % (identifier, release_id))


def _evidence_map(index: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in index.get("evidence", []) if isinstance(item, dict) and "id" in item}


def _check_evidence_ids(index: Dict[str, Any], ids: Iterable[str], path: str, errors: List[str]) -> None:
    by_id = _evidence_map(index)
    for identifier in ids:
        record = by_id.get(identifier)
        if record is None:
            _add(errors, path, "证据 %s 未登记" % identifier)
        elif record.get("result") != "passed":
            _add(errors, path, "证据 %s 的结果不是 passed" % identifier)


def _check_paths(root: Path, paths: Iterable[str], path: str, errors: List[str]) -> None:
    for relative in paths:
        if not isinstance(relative, str):
            continue
        candidate = (root / relative).resolve()
        if not is_within(root, candidate):
            _add(errors, path, "路径越出项目目录: %s" % relative)
        elif not candidate.exists():
            _add(errors, path, "路径不存在: %s" % relative)


def _stage_specific(stage: str, root: Path, artifacts: Dict[str, Dict[str, Any]], index: Dict[str, Any], approval: Optional[Dict[str, Any]], errors: List[str]) -> None:
    artifact = artifacts[stage]
    if stage == "plan":
        applicable = [item for item in artifact.get("standards", []) if item.get("status") == "applicable"]
        if not applicable:
            _add(errors, "plan.standards", "至少需要一个适用标准，不能自行宣称合规")
        if not artifact.get("vv_strategy", {}).get("independence_required"):
            _add(errors, "plan.vv_strategy", "核能软件计划必须要求独立 V&V")
        for position, person in enumerate(artifact.get("personnel", [])):
            if person.get("status") != "qualified" or not person.get("evidence", "").strip():
                _add(errors, "plan.personnel[%d]" % position, "人员必须已声明资格并附证据")
        for position, tool in enumerate(artifact.get("tool_qualification", [])):
            if tool.get("qualification_status") == "pending":
                _add(errors, "plan.tool_qualification[%d]" % position, "工具鉴定仍待完成")
    elif stage == "requirements":
        for position, requirement in enumerate(artifact.get("requirements", [])):
            for criterion_position, criterion in enumerate(requirement.get("acceptance_criteria", [])):
                if not criterion.get("method", "").strip() or not criterion.get("evidence_kind", "").strip():
                    _add(errors, "requirements[%d].acceptance_criteria[%d]" % (position, criterion_position), "验收准则必须包含方法和证据类型")
    elif stage == "implementation":
        source_control = artifact.get("source_control", {})
        if source_control.get("dirty"):
            _add(errors, "implementation.source_control", "源码工作区必须干净，不能冻结未提交修改")
        for position, module in enumerate(artifact.get("modules", [])):
            _check_paths(root, module.get("paths", []), "implementation.modules[%d].paths" % position, errors)
        _check_evidence_ids(index, artifact.get("build_evidence_ids", []), "implementation.build_evidence_ids", errors)
    elif stage == "test":
        tests = artifact.get("tests", [])
        levels = {item.get("level") for item in tests}
        categories = {item.get("category") for item in tests}
        for required in ["unit", "model", "system"]:
            if required not in levels:
                _add(errors, "test.tests", "缺少 %s 级测试" % required)
        for required in ["conservation", "boundary", "negative"]:
            if required not in categories:
                _add(errors, "test.tests", "缺少 %s 测试" % required)
        for position, test in enumerate(tests):
            if test.get("result") != "passed":
                _add(errors, "test.tests[%d]" % position, "测试结果不是 passed")
            _check_evidence_ids(index, test.get("evidence_ids", []), "test.tests[%d].evidence_ids" % position, errors)
        regression = artifact.get("regression", {})
        if regression.get("result") != "passed":
            _add(errors, "test.regression", "回归测试未通过")
        _check_evidence_ids(index, regression.get("evidence_ids", []), "test.regression.evidence_ids", errors)
    elif stage == "vv":
        independence = artifact.get("independence", {})
        developer_orgs = set(independence.get("developer_organizations", []))
        executor = independence.get("vv_executor", {})
        reviewer = independence.get("reviewer", {})
        if executor.get("name") == reviewer.get("name"):
            _add(errors, "vv.independence", "V&V 执行者与审核者必须是不同的人")
        if not executor.get("independent") or not reviewer.get("independent"):
            _add(errors, "vv.independence", "执行者和审核者都必须声明独立于开发方")
        if executor.get("organization") in developer_orgs:
            _add(errors, "vv.independence.vv_executor", "执行者组织不能是开发组织")
        if reviewer.get("organization") in developer_orgs:
            _add(errors, "vv.independence.reviewer", "审核者组织不能是开发组织")
        activity_types = {item.get("type") for item in artifact.get("activities", [])}
        for required in ["code_verification", "solution_verification", "validation"]:
            if required not in activity_types:
                _add(errors, "vv.activities", "缺少 %s 活动" % required)
        for position, activity in enumerate(artifact.get("activities", [])):
            if activity.get("result") != "passed":
                _add(errors, "vv.activities[%d]" % position, "V&V 结果不是 passed")
            if not activity.get("requirement_ids") and not activity.get("test_ids"):
                _add(errors, "vv.activities[%d]" % position, "活动必须关联需求或测试")
            if activity.get("type") == "validation":
                for key in ["benchmark_source", "applicability_domain", "uncertainty", "error_metrics", "trends"]:
                    if not activity.get(key):
                        _add(errors, "vv.activities[%d].%s" % (position, key), "确认活动缺少该字段")
            elif activity.get("type") == "code_verification" and not activity.get("reference_solution"):
                _add(errors, "vv.activities[%d].reference_solution" % position, "代码验证缺少参考解或验证方法")
            elif activity.get("type") == "solution_verification":
                for key in ["convergence_study", "observed_order"]:
                    if not activity.get(key):
                        _add(errors, "vv.activities[%d].%s" % (position, key), "解的验证缺少该字段")
            _check_evidence_ids(index, activity.get("evidence_ids", []), "vv.activities[%d].evidence_ids" % position, errors)
        if approval:
            approver = approval.get("approver", {})
            if approver.get("name") in {executor.get("name"), reviewer.get("name")}:
                _add(errors, "approval.approver", "V&V 最终批准人不能是执行者或审核者")
            if approver.get("organization") in developer_orgs:
                _add(errors, "approval.approver", "V&V 最终批准人不能来自开发组织")
    elif stage == "release":
        implementation = artifacts.get("implementation", {})
        if artifact.get("source_revision") != implementation.get("source_control", {}).get("revision"):
            _add(errors, "release.source_revision", "发布版本必须与已实现源码 revision 一致")
        _check_paths(root, artifact.get("release_scope", []), "release.release_scope", errors)
        sbom = artifact.get("sbom", {})
        _check_paths(root, [sbom.get("path", "")], "release.sbom.path", errors)
        _check_evidence_ids(index, [sbom.get("evidence_id", "")], "release.sbom.evidence_id", errors)
        reproducibility = artifact.get("reproducibility", {})
        if not reproducibility.get("verified"):
            _add(errors, "release.reproducibility", "复现性尚未验证")
        _check_evidence_ids(index, reproducibility.get("evidence_ids", []), "release.reproducibility.evidence_ids", errors)
        rollback = artifact.get("rollback", {})
        if not rollback.get("verified"):
            _add(errors, "release.rollback", "回滚方案尚未验证")
        _check_evidence_ids(index, rollback.get("evidence_ids", []), "release.rollback.evidence_ids", errors)


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def stage_gate(root: Path, stage: str, include_dependencies: bool = True) -> List[str]:
    if stage not in STAGES:
        return ["未知阶段: %s" % stage]
    errors: List[str] = []
    project_file = state_path(root) / "project.json"
    if not project_file.exists():
        return ["未初始化: 先运行 nuclearctl.py init"]
    if include_dependencies:
        index = STAGES.index(stage)
        for dependency in STAGES[:index]:
            dependency_errors = stage_gate(root, dependency, include_dependencies=True)
            if dependency_errors:
                errors.append("前置阶段 %s 未通过" % dependency)
                errors.extend("  " + item for item in dependency_errors)
    artifact_file = stage_path(root, stage)
    if not artifact_file.exists():
        errors.append("缺少阶段产物: %s" % STAGE_ARTIFACTS[stage])
        return _dedupe(errors)
    try:
        artifact = load_json(artifact_file)
    except NuclearError as exc:
        return _dedupe(errors + [str(exc)])
    errors.extend(validate_artifact(stage, artifact))
    trace_file = state_path(root) / "traceability.json"
    evidence_file = state_path(root) / "evidence" / "index.json"
    if not trace_file.exists() or not evidence_file.exists():
        errors.append("缺少 traceability.json 或 evidence/index.json")
        return _dedupe(errors)
    trace = load_json(trace_file)
    evidence_index = load_json(evidence_file)
    trace_errors: List[str] = []
    evidence_errors: List[str] = []
    validate_traceability(root, trace, trace_errors)
    validate_evidence(root, evidence_index, evidence_errors)
    errors.extend(trace_errors)
    errors.extend(evidence_errors)
    _check_trace_nodes(stage, artifact, trace, errors)
    artifacts: Dict[str, Dict[str, Any]] = {stage: artifact}
    for prior in STAGES[:STAGES.index(stage)]:
        path = stage_path(root, prior)
        if path.exists():
            try:
                artifacts[prior] = load_json(path)
            except NuclearError:
                pass
    if stage in ["design", "implementation", "test", "vv", "release"]:
        needed = {
            "design": ["requirements"],
            "implementation": ["design"],
            "test": ["implementation", "requirements"],
            "vv": ["requirements", "test"],
            "release": ["requirements", "implementation"],
        }[stage]
        if all(name in artifacts for name in needed):
            _check_links(stage, artifacts, trace, errors)
        else:
            errors.append("缺少跨阶段追溯所需的前置产物")
    approval = None
    approval_errors = validate_approval(root, stage)
    errors.extend(approval_errors)
    if not approval_errors:
        approval = load_json(approval_path(root, stage))
    _stage_specific(stage, root, artifacts, evidence_index, approval, errors)
    return _dedupe(errors)


def stage_status(root: Path) -> Dict[str, Dict[str, Any]]:
    result = {}
    for stage in STAGES:
        errors = stage_gate(root, stage, include_dependencies=False)
        result[stage] = {"passed": not errors, "errors": errors}
    return result


def add_evidence(root: Path, source: str, kind: str, producer: str, command: str, result: str, captured_at: Optional[str] = None) -> Dict[str, Any]:
    if result not in ["passed", "failed", "observed", "not_applicable"]:
        raise NuclearError("证据 result 必须为 passed/failed/observed/not_applicable")
    candidate = (root / source).resolve() if not Path(source).is_absolute() else Path(source).resolve()
    if not is_within(root, candidate):
        raise NuclearError("证据文件必须位于项目目录内")
    if not candidate.is_file():
        raise NuclearError("证据文件不存在: %s" % candidate)
    index_file = state_path(root) / "evidence" / "index.json"
    index = load_json(index_file)
    relative = relative_to_root(root, candidate)
    existing = [item for item in index.get("evidence", []) if item.get("path") == relative]
    if existing:
        raise NuclearError("该路径已登记证据 %s；请使用不同文件或先人工处理索引" % existing[0].get("id"))
    number = 1
    used = {item.get("id") for item in index.get("evidence", [])}
    while "EVID-%03d" % number in used:
        number += 1
    record = {
        "id": "EVID-%03d" % number,
        "kind": kind,
        "path": relative,
        "sha256": sha256_file(candidate),
        "captured_at": captured_at or utc_now(),
        "producer": producer,
        "command": command,
        "result": result,
    }
    index.setdefault("evidence", []).append(record)
    atomic_write_json(index_file, index)
    return record


def _iter_files(root: Path, relative: str, errors: List[str]) -> List[Path]:
    candidate = (root / relative).resolve()
    if not is_within(root, candidate):
        errors.append("发布范围越出项目目录: %s" % relative)
        return []
    if not candidate.exists():
        errors.append("发布范围不存在: %s" % relative)
        return []
    if candidate.is_symlink():
        errors.append("发布范围不能包含符号链接: %s" % relative)
        return []
    if candidate.is_file():
        return [candidate]
    files = []
    for child in sorted(candidate.rglob("*")):
        if child.is_symlink():
            errors.append("发布范围包含符号链接: %s" % relative_to_root(root, child))
        elif child.is_file() and ".nuclear-dev" not in child.parts:
            files.append(child)
    return files


def build_manifest(root: Path, version: str, force: bool = False) -> Tuple[Path, Dict[str, Any]]:
    gate_errors = stage_gate(root, "release")
    if gate_errors:
        raise NuclearError("发布门禁未通过，不能生成清单:\n" + "\n".join("- " + item for item in gate_errors))
    release = load_json(stage_path(root, "release"))
    if release.get("version") != version:
        raise NuclearError("版本不匹配: release=%s, requested=%s" % (release.get("version"), version))
    errors: List[str] = []
    files: List[Path] = []
    seen = set()
    for relative in release.get("release_scope", []):
        for file_path in _iter_files(root, relative, errors):
            key = relative_to_root(root, file_path)
            if key not in seen:
                seen.add(key)
                files.append(file_path)
    if errors:
        raise NuclearError("发布范围无效:\n" + "\n".join("- " + item for item in errors))
    files.sort(key=lambda item: relative_to_root(root, item))
    file_records = [
        {"path": relative_to_root(root, path), "size": path.stat().st_size, "sha256": sha256_file(path)}
        for path in files
    ]
    assurance_paths = [state_path(root) / STAGE_ARTIFACTS[stage] for stage in STAGES]
    assurance_paths += [state_path(root) / "traceability.json", state_path(root) / "evidence" / "index.json"]
    assurance_paths += [approval_path(root, stage) for stage in STAGES]
    evidence_index = load_json(state_path(root) / "evidence" / "index.json")
    for record in evidence_index.get("evidence", []):
        if isinstance(record, dict) and isinstance(record.get("path"), str):
            assurance_paths.append((root / record["path"]).resolve())
    assurance_files = []
    assurance_seen = set()
    for path in assurance_paths:
        if path.exists() and path.is_file():
            key = relative_to_root(root, path)
            if key not in assurance_seen and ".nuclear-dev/manifests" not in key:
                assurance_seen.add(key)
                assurance_files.append({"path": key, "size": path.stat().st_size, "sha256": sha256_file(path)})
    assurance_files.sort(key=lambda item: item["path"])
    project = project_metadata(root)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kit": {"name": "nuclear-dev-kit", "version": KIT_VERSION},
        "software": {"name": project.get("name"), "release_id": release.get("release_id"), "version": version},
        "source_revision": release.get("source_revision"),
        "configuration": release.get("configuration"),
        "files": file_records,
        "assurance": assurance_files,
        "sbom": release.get("sbom"),
        "known_limitations": release.get("known_limitations", []),
        "digest_algorithm": "sha256",
    }
    destination = state_path(root) / "manifests" / ("software-configuration-manifest-%s.json" % version)
    if destination.exists():
        existing = load_json(destination)
        if existing != manifest and not force:
            raise NuclearError("清单已存在且内容不同；确认后使用 --force 覆盖: %s" % destination)
    atomic_write_json(destination, manifest)
    return destination, manifest
