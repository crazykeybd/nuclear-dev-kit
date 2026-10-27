#!/usr/bin/env python3
"""把 nuclear-dev-kit 的十个 Skill 安装到受支持的 Agent 宿主。"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = PACKAGE_ROOT
SOURCE_ROOT = SKILLS_ROOT / "skills" if (SKILLS_ROOT / "skills").is_dir() else SKILLS_ROOT
SKILL_NAMES = [
    "nuclear-dev",
    "nuclear-setup",
    "nuclear-install",
    "nuclear-plan",
    "nuclear-requirements",
    "nuclear-design",
    "nuclear-implementation",
    "nuclear-test",
    "nuclear-vv",
    "nuclear-release",
]
HOSTS = ["claude", "codex", "opencode", "reasonix", "generic"]
BACKUP_DIR = ".nuclear-dev-kit-backups"


class InstallError(Exception):
    """安装参数、源包或文件操作失败。"""


class ChineseHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> str:
        text = action.help or ""
        if action.default is not argparse.SUPPRESS and "%(default)" not in text:
            if action.option_strings and action.default not in (None, False, argparse.SUPPRESS):
                text += "（默认: %(default)s）"
        return text


class ChineseArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "错误: %s\n使用 --help 查看中文帮助。\n" % message)

    def format_help(self) -> str:
        text = super().format_help()
        replacements = {
            "usage:": "用法:",
            "positional arguments:": "位置参数:",
            "options:": "选项:",
            "optional arguments:": "选项:",
            "show this help message and exit": "显示帮助并退出",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text


def emit_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def home_dir() -> Path:
    return Path.home().resolve()


def environment_root(variable: str, fallback: Path) -> Path:
    value = os.environ.get(variable)
    base = Path(value).expanduser() if value else fallback
    return base.resolve()


def reasonix_home() -> Path:
    """Reasonix 的 home：REASONIX_HOME > Windows %APPDATA%/reasonix > ~/.reasonix。"""
    value = os.environ.get("REASONIX_HOME")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (Path(appdata) / "reasonix").resolve()
        return (home_dir() / "AppData" / "Roaming" / "reasonix").resolve()
    return (home_dir() / ".reasonix").resolve()


def host_roots(project: Optional[Path]) -> Dict[str, Path]:
    if project is None:
        raise InstallError("project 范围为必填参数：请使用 --project 指定项目目录")
    return {
        "claude": project / ".claude" / "skills",
        "codex": project / ".agents" / "skills",
        "opencode": project / ".opencode" / "skills",
        "reasonix": project / ".reasonix" / "skills",
        "generic": project / ".agents" / "skills",
    }


def global_host_roots() -> Dict[str, Path]:
    home = home_dir()
    return {
        "claude": home / ".claude" / "skills",
        "codex": environment_root("CODEX_HOME", home / ".codex") / "skills",
        "opencode": home / ".config" / "opencode" / "skills",
        "reasonix": reasonix_home() / "skills",
        "generic": home / ".agents" / "skills",
    }


def resolve_roots(host: str, scope: str, project: Optional[str]) -> List[Tuple[str, Path]]:
    if scope == "project":
        project_root = Path(project).expanduser().resolve() if project else None
        roots = host_roots(project_root)
    else:
        if project:
            project = None
        roots = global_host_roots()
    selected = HOSTS if host == "all" else [host]
    unique: Dict[str, Tuple[str, Path]] = {}
    for name in selected:
        path = roots[name].resolve()
        key = os.path.normcase(str(path))
        if key not in unique:
            unique[key] = (name, path)
    return list(unique.values())


def iter_source_files(source: Path) -> List[Tuple[Path, str]]:
    files: List[Tuple[Path, str]] = []
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue
        if item.is_symlink():
            raise InstallError("Skill 源包含符号链接，拒绝安装: %s" % item)
        if item.is_file():
            files.append((item, relative.as_posix()))
    return files


def validate_sources() -> List[Tuple[str, Path]]:
    sources: List[Tuple[str, Path]] = []
    missing = []
    for name in SKILL_NAMES:
        source = SOURCE_ROOT / name
        marker = source / "SKILL.md"
        if not source.is_dir() or not marker.is_file():
            missing.append(str(marker))
        else:
            sources.append((name, source))
    if missing:
        raise InstallError("安装源不完整，缺少:\n" + "\n".join("- " + item for item in missing))
    return sources


def target_plan(hosts: Sequence[Tuple[str, Path]], force: bool) -> Tuple[List[Dict[str, Any]], List[str]]:
    targets: List[Dict[str, Any]] = []
    conflicts: List[str] = []
    for host, root in hosts:
        for name, source in validate_sources():
            destination = root / name
            exists = destination.exists() or destination.is_symlink()
            if exists and not force:
                conflicts.append("%s (%s): 已存在 %s" % (name, host, destination))
            targets.append(
                {
                    "host": host,
                    "name": name,
                    "source": str(source),
                    "destination": str(destination),
                    "exists": exists,
                }
            )
    return targets, conflicts


def copy_filtered(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for item, relative in iter_source_files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(item), str(target))


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def backup_destination(root: Path, name: str, stamp: str) -> Path:
    return root / BACKUP_DIR / stamp / name


def make_backups(targets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    backups: List[Dict[str, Any]] = []
    stamp = timestamp()
    for target in targets:
        destination = Path(target["destination"])
        if not target["exists"]:
            continue
        destination_root = destination.parent
        backup = backup_destination(destination_root, target["name"], stamp)
        if backup.exists() or backup.is_symlink():
            raise InstallError("备份目标已存在: %s" % backup)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise InstallError("拒绝覆盖符号链接目标: %s" % destination)
        shutil.copytree(str(destination), str(backup), symlinks=True)
        backups.append({"host": target["host"], "name": target["name"], "path": str(backup)})
    return backups


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(str(path))


def install_atomically(targets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    staged: List[Dict[str, Any]] = []
    replaced: List[Dict[str, Any]] = []
    backups: List[Dict[str, Any]] = []
    try:
        for target in targets:
            destination = Path(target["destination"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".%s." % target["name"], dir=str(destination.parent)))
            staged_path = staging / target["name"]
            try:
                copy_filtered(Path(target["source"]), staged_path)
            except Exception:
                remove_path(staging)
                raise
            staged.append({"target": target, "root": staging, "path": staged_path})
        backups = make_backups(targets)
        for item in staged:
            target = item["target"]
            destination = Path(target["destination"])
            if target["exists"]:
                discarded = item["root"] / (target["name"] + ".previous")
                os.replace(str(destination), str(discarded))
                item["discarded"] = discarded
                replaced.append(item)
            os.replace(str(item["path"]), str(destination))
            if item not in replaced:
                replaced.append(item)
    except Exception as exc:
        rollback_errors: List[str] = []
        for item in reversed(replaced):
            target = item["target"]
            destination = Path(target["destination"])
            try:
                remove_path(destination)
                previous = item.get("discarded")
                if previous is not None and previous.exists():
                    os.replace(str(previous), str(destination))
            except Exception as rollback_exc:
                rollback_errors.append("%s: %s" % (destination, rollback_exc))
        for item in staged:
            try:
                remove_path(item["root"])
            except Exception as rollback_exc:
                rollback_errors.append("%s: %s" % (item["root"], rollback_exc))
        detail = "安装失败并已尝试回滚: %s" % exc
        if rollback_errors:
            detail += "\n回滚异常:\n" + "\n".join("- " + error for error in rollback_errors)
        if backups:
            detail += "\n已创建备份:\n" + "\n".join("- " + backup["path"] for backup in backups)
        raise InstallError(detail)
    for item in staged:
        remove_path(item["root"])
    return backups


def install_by_host(
    targets: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按宿主分组安装：一个宿主失败只回滚它自己的一组，其余宿主照常写入。

    整批回滚会让一个被占用的宿主目录拖垮全部宿主；按宿主分组既保留单宿主内的
    全有或全无，又不会让失败扩散。
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for target in targets:
        groups.setdefault(target["host"], []).append(target)
    backups: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for host, group in groups.items():
        try:
            backups.extend(install_atomically(group))
        except InstallError as exc:
            failures.append({"host": host, "error": str(exc)})
    return backups, failures


def build_parser() -> ChineseArgumentParser:
    parser = ChineseArgumentParser(
        description="把 nuclear-dev-kit 的十个 Skill 安装到 Claude Code、Codex、opencode、Reasonix 或通用 Agent。",
        epilog=(
            "安全边界: 默认 dry-run；只有 --yes 且未显式指定 --dry-run 才写入。\n"
            "安装器不修改宿主配置、项目源码或批准文件。"
        ),
        formatter_class=ChineseHelpFormatter,
    )
    parser.add_argument("host", choices=HOSTS + ["all"], help="目标宿主；all 表示全部宿主")
    parser.add_argument("--scope", choices=["project", "global"], default="project", help="安装范围")
    parser.add_argument("--project", metavar="路径", help="项目根目录；project 范围必填")
    parser.add_argument("--dry-run", action="store_true", help="只预检并输出计划，不写入文件")
    parser.add_argument("--yes", action="store_true", help="确认执行写入")
    parser.add_argument("--force", action="store_true", help="允许备份并覆盖已存在的同名 Skill")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def execute(args: argparse.Namespace) -> Tuple[int, Dict[str, Any]]:
    if args.scope == "project" and not args.project:
        raise InstallError("project 范围必须提供 --project")
    project = args.project if args.scope == "project" else None
    roots = resolve_roots(args.host, args.scope, project)
    targets, conflicts = target_plan(roots, args.force)
    dry_run = args.dry_run or not args.yes
    payload: Dict[str, Any] = {
        "ok": not conflicts,
        "dry_run": dry_run,
        "hosts": [name for name, _ in roots],
        "targets": targets,
        "conflicts": conflicts,
        "status": "conflict" if conflicts else ("planned" if dry_run else "installed"),
    }
    if conflicts:
        return 1, payload
    if dry_run:
        return 0, payload
    backups, failures = install_by_host(targets)
    payload["backups"] = [str(item["path"]) for item in backups]
    if failures:
        payload["ok"] = False
        payload["status"] = "partial"
        payload["failures"] = failures
        return 2, payload
    return 0, payload


def print_human(payload: Dict[str, Any]) -> None:
    print("状态: %s" % payload["status"])
    print("宿主: %s" % ", ".join(payload["hosts"]))
    print("目标数: %d" % len(payload["targets"]))
    if payload["conflicts"]:
        print("冲突:")
        for conflict in payload["conflicts"]:
            print("- %s" % conflict)
    elif payload["dry_run"]:
        print("dry-run 未写入；确认后使用 --yes。")
    elif payload.get("failures"):
        print("以下宿主安装失败（其余宿主已写入）:")
        for failure in payload["failures"]:
            print("- %s: %s" % (failure["host"], failure["error"]))
    else:
        print("安装完成；未修改宿主配置、项目源码或批准文件。")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, payload = execute(args)
    except InstallError as exc:
        payload = {
            "ok": False,
            "dry_run": bool(getattr(args, "dry_run", False) or not getattr(args, "yes", False)),
            "hosts": [],
            "targets": [],
            "conflicts": [],
            "status": "error",
            "error": str(exc),
        }
        if args.json:
            emit_json(payload)
        else:
            print("错误: %s" % exc, file=sys.stderr)
            print("使用 --help 查看中文帮助。", file=sys.stderr)
        return 2
    if args.json:
        emit_json(payload)
    else:
        print_human(payload)
    return code


if __name__ == "__main__":
    sys.exit(main())
