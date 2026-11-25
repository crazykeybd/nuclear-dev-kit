#!/usr/bin/env python3
"""把 process-assets 的 40 个 Skill 安装到 Agent 宿主，独立于 nuclear-* 安装器。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "skills"
HOSTS = ["claude", "codex", "opencode", "reasonix", "generic", "dsh"]
BACKUP_DIR = ".nuclear-dev-kit-backups"


class InstallError(Exception):
    pass


def emit_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def home() -> Path:
    return Path.home().resolve()


def env_root(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return (Path(value).expanduser() if value else fallback).resolve()


def reasonix_home() -> Path:
    value = os.environ.get("REASONIX_HOME")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return (Path(appdata) / "reasonix").resolve() if appdata else (home() / "AppData" / "Roaming" / "reasonix").resolve()
    return home() / ".reasonix"


def host_roots(project: Optional[Path]) -> Dict[str, Path]:
    if project is None:
        raise InstallError("project 范围为必填参数：请提供 --project")
    return {
        "claude": project / ".claude" / "skills",
        "codex": project / ".agents" / "skills",
        "opencode": project / ".opencode" / "skills",
        "reasonix": project / ".reasonix" / "skills",
        "generic": project / ".agents" / "skills",
        "dsh": project / ".dsh" / "skills",
    }


def global_roots() -> Dict[str, Path]:
    h = home()
    return {
        "claude": h / ".claude" / "skills",
        "codex": env_root("CODEX_HOME", h / ".codex") / "skills",
        "opencode": h / ".config" / "opencode" / "skills",
        "reasonix": reasonix_home() / "skills",
        "generic": h / ".agents" / "skills",
        "dsh": env_root("DSH_HOME", h / ".dsh") / "skills",
    }


def resolve(host: str, scope: str, project: Optional[str]) -> List[Tuple[str, Path]]:
    if host == "all":
        return [(name, root) for name, root in host_roots(Path(project).expanduser().resolve() if scope == "project" else None).items()] \
            if scope == "project" else list(global_roots().items())
    roots = host_roots(Path(project).expanduser().resolve() if scope == "project" else None) if scope == "project" else global_roots()
    if host not in roots:
        raise InstallError("未知宿主: %s" % host)
    return [(host, roots[host])]


def source_dirs() -> List[Path]:
    return sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())


def plan(host: str, scope: str, project: Optional[str]) -> Dict[str, Any]:
    targets: List[Dict[str, Any]] = []
    for _, root in resolve(host, scope, project):
        for source in source_dirs():
            targets.append({"source": str(source), "target": str(root / source.name), "status": "new"})
    conflicts = [item for item in targets if Path(item["target"]).exists()]
    for item in conflicts:
        item["status"] = "conflict"
    return {"command": "install", "host": host, "scope": scope, "count": len(targets),
            "targets": targets, "conflicts": conflicts, "dry_run": True}


def install(host: str, scope: str, project: Optional[str], force: bool) -> Dict[str, Any]:
    payload = plan(host, scope, project)
    if payload["conflicts"] and not force:
        payload["status"] = "conflict"
        return payload
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    written: List[str] = []
    for item in payload["targets"]:
        target = Path(item["target"])
        if target.exists() and force:
            backup_root = target.parent / BACKUP_DIR / stamp
            backup_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup_root / target.name, dirs_exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(target.parent)) as temp:
            staging = Path(temp) / target.name
            shutil.copytree(item["source"], staging,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if target.exists():
                shutil.rmtree(str(target))
            os.replace(str(staging), str(target))
        written.append(str(target))
    payload.update({"status": "ok", "dry_run": False, "written": written, "backup": stamp if force else None})
    return payload


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="安装 process-assets Skill 包（默认 dry-run）。")
    parser.add_argument("host", nargs="?", default="auto", choices=["auto"] + HOSTS + ["all"])
    parser.add_argument("--host", dest="host_opt", choices=HOSTS + ["all"], help="宿主（与位置参数等价）")
    parser.add_argument("--scope", choices=["project", "global"], default="global")
    parser.add_argument("--project", help="项目根目录（--scope project 必填）")
    parser.add_argument("--yes", action="store_true", help="确认写入；缺省为 dry-run")
    parser.add_argument("--force", action="store_true", help="备份并覆盖已存在 Skill")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)
    host = args.host_opt or args.host
    try:
        payload = plan(host, args.scope, args.project) if not args.yes else install(host, args.scope, args.project, args.force)
    except InstallError as exc:
        sys.stderr.write("错误: %s\n" % exc)
        return 2
    if args.json:
        emit_json(payload)
    else:
        print("宿主: %s, 范围: %s, Skill: %d" % (payload["host"], payload["scope"], payload["count"]))
        print("状态: %s" % payload.get("status", "dry-run"))
        if payload.get("conflicts"):
            print("冲突: %d 个目标已存在（--force 可备份覆盖）" % len(payload["conflicts"]))
    return 1 if payload.get("status") == "conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
