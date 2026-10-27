#!/usr/bin/env python3
"""检查 nuclear-dev-kit 在 Reasonix 上的部署状态（只读）。

用途：会话开始时判断「是否已部署」「是否需要更新」，不修改任何文件。

状态取值：

- `not_deployed`   Reasonix home 或 skills 目录不存在
- `partial`        只装了部分 Skill
- `needs_update`   Skill 文件与当前源码不一致
- `config_missing` Skill 齐全但 config.toml 未注册 nuclear-dev
- `up_to_date`     文件一致且已注册

退出码：0 = up_to_date，1 = 其余状态（需要用户决定是否部署或更新）。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO / "skills"
SERVER_NAME = "nuclear-dev"
IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc"}


def reasonix_home() -> Path:
    value = os.environ.get("REASONIX_HOME")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (Path(appdata) / "reasonix").resolve()
        return (Path.home() / "AppData" / "Roaming" / "reasonix").resolve()
    return (Path.home() / ".reasonix").resolve()


def skill_names() -> List[str]:
    return sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir())


def manifest(root: Path) -> Dict[str, str]:
    """相对路径 → SHA256；跳过缓存与临时文件。"""
    entries: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in IGNORED_SUFFIXES or not path.is_file():
            continue
        entries[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def plugin_registered(config: Path) -> bool:
    if not config.is_file():
        return False
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return False
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[plugins]]":
            in_block = True
            continue
        if stripped.startswith("[") and stripped != "[[plugins]]":
            in_block = False
            continue
        if in_block and stripped.startswith("name") and "=" in stripped:
            value = stripped.partition("=")[2].strip().strip('"')
            if value == SERVER_NAME:
                return True
    return False


def inspect(home: Optional[Path] = None) -> Dict[str, Any]:
    home = home or reasonix_home()
    installed_root = home / "skills"
    config = home / "config.toml"
    expected = skill_names()

    result: Dict[str, Any] = {
        "ok": False,
        "reasonix_home": str(home),
        "skills_dir": str(installed_root),
        "config_path": str(config),
        "expected_skills": expected,
        "installed_skills": [],
        "missing_skills": [],
        "changed_skills": [],
        "extra_skills": [],
        "plugin_registered": plugin_registered(config),
    }

    if not installed_root.is_dir():
        result["status"] = "not_deployed"
        result["missing_skills"] = expected
        return result

    # 跳过以点开头的目录：安装器的 --force 备份放在 skills/.nuclear-dev-kit-backups，
    # 它不是 Skill，算进 extra_skills 会让每次强制升级后都误报 partial。
    present = sorted(
        path.name for path in installed_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    result["installed_skills"] = [name for name in present if name in expected]
    result["missing_skills"] = [name for name in expected if name not in present]
    result["extra_skills"] = [name for name in present if name not in expected]

    for name in result["installed_skills"]:
        if manifest(SKILLS_ROOT / name) != manifest(installed_root / name):
            result["changed_skills"].append(name)

    if result["missing_skills"] or result["extra_skills"]:
        status = "partial"
    elif result["changed_skills"]:
        status = "needs_update"
    elif not result["plugin_registered"]:
        status = "config_missing"
    else:
        status = "up_to_date"

    result["status"] = status
    result["ok"] = status == "up_to_date"
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_reasonix_deploy.py",
        description="检查 Reasonix 上的 Skill 与 MCP 注册状态；只读，不修改文件。",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--home", metavar="路径", help="指定 Reasonix home，默认按 REASONIX_HOME / APPDATA 推导")
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser().resolve() if args.home else None
    result = inspect(home)

    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        print("状态: %s" % result["status"])
        print("Reasonix home: %s" % result["reasonix_home"])
        print("Skill 目录: %s" % result["skills_dir"])
        print("MCP 已注册: %s" % ("是" if result["plugin_registered"] else "否"))
        if result["missing_skills"]:
            print("缺失: %s" % ", ".join(result["missing_skills"]))
        if result["changed_skills"]:
            print("有变更: %s" % ", ".join(result["changed_skills"]))
        if result["extra_skills"]:
            print("多余（非本包）: %s" % ", ".join(result["extra_skills"]))
        if result["status"] != "up_to_date":
            print("建议: 询问用户是否部署或更新；不要自动写入。")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
