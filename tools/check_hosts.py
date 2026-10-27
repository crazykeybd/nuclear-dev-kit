#!/usr/bin/env python3
"""宿主能力矩阵一致性校验（只读）。

宿主路径与注册格式目前分布在三个脚本里：

- `skills/nuclear-setup/scripts/install.py`       安装目标路径与服务端脚本定位
- `skills/nuclear-install/scripts/quickinstall.py` 宿主检测与便捷安装
- `skills/nuclear-install/scripts/register.py`      MCP 注册片段生成

三处必须给出同一套宿主集合与同一套路径。本脚本把它们读出来逐项比对，
并核对 `host-compatibility.md` 的宿主表是否覆盖全部宿主。

为什么不做代码合并：每个 Skill 要能整棵复制后独立工作，跨 Skill 的运行时
import 会破坏这一前提。因此这里选择「显式校验」而不是「隐式共享」。

已知限制写在 `KNOWN_EXCLUSIONS` 里；新增限制必须同步写进这里，否则校验会失败。

退出码：0 一致，1 有不一致。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "install": REPO / "skills" / "nuclear-setup" / "scripts" / "install.py",
    "quickinstall": REPO / "skills" / "nuclear-install" / "scripts" / "quickinstall.py",
    "register": REPO / "skills" / "nuclear-install" / "scripts" / "register.py",
}
HOST_DOCS = [
    REPO / "skills" / "nuclear-dev" / "references" / "host-compatibility.md",
    REPO / "skills" / "nuclear-setup" / "references" / "host-compatibility.md",
]

# 已知且有意的差异：宿主 id → 原因。出现未登记的差异即视为不一致。
KNOWN_EXCLUSIONS = {
    ("register", "project", "opencode"): "opencode 的 MCP 配置格式未实测，register.py 不生成片段",
    ("register", "global", "opencode"): "opencode 的 MCP 配置格式未实测，register.py 不生成片段",
}


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("hosts_check_" + name, str(path))
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载模块: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def project_roots(module_name: str, module: Any, project: Path) -> Dict[str, str]:
    """统一返回相对项目根的路径，避免绝对路径与平台分隔符影响比较。"""
    if module_name == "install":
        return {
            host: path.relative_to(project).as_posix()
            for host, path in module.host_roots(project).items()
        }
    if module_name == "register":
        return {host: path.as_posix() for host, path in module.PROJECT_SKILL_ROOTS.items()}
    return {}


def global_roots(module_name: str, module: Any) -> Dict[str, str]:
    if module_name == "install":
        return {host: str(path) for host, path in module.global_host_roots().items()}
    if module_name == "register":
        return {host: str(path) for host, path in module.global_skill_roots().items()}
    return {}


def diff(mapping: str, reference_name: str, reference: Dict[str, str], actual_name: str,
         actual: Dict[str, str]) -> List[str]:
    problems: List[str] = []
    for host, value in reference.items():
        if host in actual:
            if actual[host] != value:
                problems.append(
                    "%s 的 %s 路径不一致：%s=%s，%s=%s"
                    % (host, mapping, reference_name, value, actual_name, actual[host])
                )
            continue
        if (actual_name, mapping, host) in KNOWN_EXCLUSIONS:
            continue
        problems.append(
            "%s 的 %s 在 %s 中缺失（%s 有：%s）"
            % (host, mapping, actual_name, reference_name, value)
        )
    for host in actual:
        if host not in reference:
            problems.append("%s 的 %s 在 %s 中多出，%s 未定义" % (host, mapping, actual_name, reference_name))
    return problems


def main() -> int:
    modules = {name: load(name, path) for name, path in SCRIPTS.items()}
    problems: List[str] = []

    install_hosts = list(modules["install"].HOSTS)
    for name in ("quickinstall", "register"):
        other = list(modules[name].HOSTS)
        if other != install_hosts:
            problems.append(
                "%s.HOSTS=%s 与 install.HOSTS=%s 不一致" % (name, other, install_hosts)
            )

    quick_labels = set(modules["quickinstall"].HOST_LABELS) - {"all"}
    if quick_labels != set(install_hosts):
        problems.append(
            "quickinstall.HOST_LABELS 与 install.HOSTS 不一致：%s vs %s"
            % (sorted(quick_labels), sorted(install_hosts))
        )

    sentinel = Path("/nonexistent-project")
    reference_project = project_roots("install", modules["install"], sentinel)
    for name in ("register",):
        problems.extend(
            diff(
                "project",
                "install",
                reference_project,
                name,
                project_roots(name, modules[name], sentinel),
            )
        )

    reference_global = global_roots("install", modules["install"])
    problems.extend(
        diff("global", "install", reference_global, "register", global_roots("register", modules["register"]))
    )

    for doc in HOST_DOCS:
        text = doc.read_text(encoding="utf-8")
        for host, path in reference_project.items():
            if path not in text:
                problems.append(
                    "%s 未记录宿主 %s 的项目路径 %s"
                    % (doc.relative_to(REPO).as_posix(), host, path)
                )

    if problems:
        for item in problems:
            sys.stderr.write("- %s\n" % item)
        return 1

    sys.stdout.write(
        "宿主矩阵一致：%d 个宿主，%d 份文档\n" % (len(install_hosts), len(HOST_DOCS))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
