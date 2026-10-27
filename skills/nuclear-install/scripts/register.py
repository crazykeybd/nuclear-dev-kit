#!/usr/bin/env python3
"""生成 MCP 服务端注册片段。

默认只打印，不写宿主配置。仅 Claude Code 的项目级 .mcp.json 支持 --write（写入前备份）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SKILL_DIR = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = SKILL_DIR.parents[1]
SOURCE_SERVER = PACKAGE_ROOT / "skills" / "nuclear-dev" / "scripts" / "nuclearmcp.py"
SERVER_NAME = "nuclear-dev"
HOSTS = ["claude", "codex", "opencode", "reasonix", "generic"]
HOST_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "opencode",
    "reasonix": "Reasonix",
    "generic": "通用 MCP 客户端",
}
UNSUPPORTED_HOSTS = {
    "opencode": (
        "opencode 的 MCP 配置格式（opencode.json 的 mcp 段）未在本包中实测，"
        "不生成未验证的配置。请按 opencode 官方文档手工注册，或先实测格式再扩展本工具。"
    ),
}
PROJECT_SKILL_ROOTS = {
    "claude": Path(".claude") / "skills",
    "codex": Path(".agents") / "skills",
    "reasonix": Path(".reasonix") / "skills",
    "generic": Path(".agents") / "skills",
}


class RegisterError(Exception):
    """注册参数或路径无效。"""


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


def global_skill_roots() -> Dict[str, Path]:
    home = home_dir()
    return {
        "claude": home / ".claude" / "skills",
        "codex": environment_root("CODEX_HOME", home / ".codex") / "skills",
        "reasonix": reasonix_home() / "skills",
        "generic": home / ".agents" / "skills",
    }


def install_root(host: str, scope: str, project: Optional[Path]) -> Path:
    if scope == "project":
        if project is None:
            raise RegisterError("project 范围必须提供 --project")
        return (project / PROJECT_SKILL_ROOTS[host]).resolve()
    return global_skill_roots()[host]


def resolve_server(host: str, scope: str, project: Optional[Path]) -> Tuple[Path, str]:
    installed = install_root(host, scope, project) / "nuclear-dev" / "scripts" / "nuclearmcp.py"
    if installed.is_file():
        return installed, "installed"
    if SOURCE_SERVER.is_file():
        return SOURCE_SERVER.resolve(), "source"
    raise RegisterError("找不到 nuclearmcp.py；先安装 Skill 或从源码目录运行")


def server_arguments(server: Path, workspaces: Sequence[Path], allow_write: bool) -> List[str]:
    arguments = [str(server)]
    for workspace in workspaces:
        arguments += ["--workspace", str(workspace)]
    if allow_write:
        arguments.append("--allow-write")
    return arguments


def claude_snippet(python: str, arguments: Sequence[str]) -> Dict[str, Any]:
    return {"mcpServers": {SERVER_NAME: {"command": python, "args": list(arguments)}}}


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def codex_snippet(python: str, arguments: Sequence[str]) -> str:
    lines = [
        "[mcp_servers.%s]" % SERVER_NAME,
        "command = %s" % toml_string(python),
        "args = [%s]" % ", ".join(toml_string(item) for item in arguments),
    ]
    return "\n".join(lines) + "\n"


def neutral_spec(python: str, arguments: Sequence[str]) -> Dict[str, Any]:
    return {
        "name": SERVER_NAME,
        "transport": "stdio",
        "command": python,
        "args": list(arguments),
    }


def reasonix_plugin_snippet(python: str, arguments: Sequence[str]) -> str:
    lines = [
        "[[plugins]]",
        "name = %s" % toml_string(SERVER_NAME),
        'type = "stdio"',
        "command = %s" % toml_string(python),
        "args = [%s]" % ", ".join(toml_string(item) for item in arguments),
    ]
    return "\n".join(lines) + "\n"


def config_path(host: str, scope: str, project: Optional[Path]) -> Optional[Path]:
    if host in ("claude", "reasonix") and scope == "project" and project is not None:
        return (project / ".mcp.json").resolve()
    return None


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_atomic(path: Path, text: str) -> None:
    """写临时文件再 os.replace，避免中途失败留下半截配置。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, str(path))
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def merge_claude_config(path: Path, snippet: Dict[str, Any]) -> Dict[str, Any]:
    backup = None
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as stream:
                existing = json.load(stream)
        except (OSError, ValueError) as exc:
            raise RegisterError("现有 .mcp.json 无法解析，拒绝写入: %s" % exc)
        if not isinstance(existing, dict):
            raise RegisterError("现有 .mcp.json 不是对象，拒绝写入")
        backup = path.with_name(path.name + "." + timestamp() + ".bak")
        backup.write_bytes(path.read_bytes())
    else:
        existing = {}
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RegisterError("现有 .mcp.json 的 mcpServers 不是对象，拒绝写入")
    servers[SERVER_NAME] = snippet["mcpServers"][SERVER_NAME]
    write_atomic(
        path, json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return {"path": str(path), "backup": str(backup) if backup else None}


REASONIX_MARKER = "# added by nuclear-dev-kit register.py; delete this block to unregister"


def existing_plugin_names(text: str) -> List[str]:
    """扫描 TOML 文本中每个 [[plugins]] 块的 name 值。"""
    names: List[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[plugins]]":
            in_block = True
            continue
        if stripped.startswith("[") and stripped != "[[plugins]]":
            in_block = False
            continue
        if in_block and "=" in stripped:
            key, _, value = stripped.partition("=")
            if key.strip() == "name":
                names.append(value.strip().strip('"'))
    return names


def validate_toml(text: str, path: Path) -> None:
    """可用 tomllib 时校验 TOML 语法；Python < 3.11 跳过。"""
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        tomllib.loads(text)
    except Exception as exc:
        raise RegisterError("追加后的 TOML 无法解析，已放弃写入 %s: %s" % (path, exc))


def merge_reasonix_plugins(path: Path, snippet: str, name: str) -> Dict[str, Any]:
    """把 [[plugins]] 追加到 Reasonix 全局 config.toml；先备份，重复即拒绝。"""
    if not path.is_file():
        raise RegisterError("未找到 Reasonix 全局配置: %s；请先在 Reasonix 中完成一次 setup" % path)
    original = path.read_text(encoding="utf-8")
    if name in existing_plugin_names(original):
        raise RegisterError("config.toml 已存在名为 %s 的 [[plugins]]，拒绝重复写入" % name)
    separator = "\n" if original.endswith("\n") else "\n\n"
    combined = original + separator + REASONIX_MARKER + "\n" + snippet
    validate_toml(combined, path)
    backup = path.with_name(path.name + "." + timestamp() + ".bak")
    backup.write_bytes(path.read_bytes())
    write_atomic(path, combined)
    return {"path": str(path), "backup": str(backup)}


def build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    unsupported = UNSUPPORTED_HOSTS.get(args.host)
    if unsupported:
        raise RegisterError(unsupported)
    project = Path(args.project).expanduser().resolve() if args.project else Path.cwd().resolve()
    if args.scope == "project" and not args.project:
        raise RegisterError("project 范围必须提供 --project")
    server, source_kind = resolve_server(args.host, args.scope, project)

    if args.workspace:
        workspaces = [Path(item).expanduser().resolve() for item in args.workspace]
    else:
        workspaces = [project]
    for workspace in workspaces:
        if not workspace.is_dir():
            raise RegisterError("workspace 不存在或不是目录: %s" % workspace)

    python = args.python or sys.executable
    arguments = server_arguments(server, workspaces, args.allow_write)
    payload: Dict[str, Any] = {
        "ok": True,
        "host": args.host,
        "host_label": HOST_LABELS[args.host],
        "scope": args.scope,
        "server_path": str(server),
        "server_source": source_kind,
        "python": python,
        "workspaces": [str(item) for item in workspaces],
        "allow_write": bool(args.allow_write),
        "wrote": False,
        "notes": [],
    }

    if args.host == "claude":
        payload["format"] = "json"
        payload["snippet"] = claude_snippet(python, arguments)
        target = config_path(args.host, args.scope, project)
        payload["config_path"] = str(target) if target else None
        if target is not None and args.write:
            result = merge_claude_config(target, payload["snippet"])
            payload["wrote"] = True
            payload["config_path"] = result["path"]
            payload["backup"] = result["backup"]
            payload["notes"].append("已合并写入 .mcp.json；同名服务会被覆盖。")
        elif target is not None:
            payload["notes"].append("默认不写配置；确认后加 --write 合并写入项目级 .mcp.json。")
        else:
            payload["notes"].append("全局范围请手工合并到 Claude Code 的 MCP 配置。")
    elif args.host == "codex":
        payload["format"] = "toml"
        payload["snippet"] = codex_snippet(python, arguments)
        payload["notes"].append("把片段追加到 Codex 的 config.toml；本工具不写 TOML，避免破坏既有配置。")
    elif args.host == "reasonix":
        if args.scope == "project":
            payload["format"] = "json"
            payload["snippet"] = claude_snippet(python, arguments)
            target = config_path(args.host, args.scope, project)
            payload["config_path"] = str(target) if target else None
            if target is not None and args.write:
                result = merge_claude_config(target, payload["snippet"])
                payload["wrote"] = True
                payload["config_path"] = result["path"]
                payload["backup"] = result["backup"]
                payload["notes"].append("已合并写入项目级 .mcp.json；Reasonix 会原生读取。")
            else:
                payload["notes"].append(
                    "Reasonix 原生读取项目根 .mcp.json；确认后加 --write 合并写入。"
                )
        else:
            payload["format"] = "toml"
            payload["snippet"] = reasonix_plugin_snippet(python, arguments)
            target = reasonix_home() / "config.toml"
            payload["config_path"] = str(target)
            if args.write:
                result = merge_reasonix_plugins(target, payload["snippet"], SERVER_NAME)
                payload["wrote"] = True
                payload["backup"] = result["backup"]
                payload["notes"].append(
                    "已追加 [[plugins]] 到 Reasonix config.toml；重启会话或等待热加载生效。"
                )
            else:
                payload["notes"].append(
                    "把 [[plugins]] 片段追加到 Reasonix 的 config.toml；加 --write 可自动追加（写入前备份）。"
                )
    else:
        payload["format"] = "json"
        payload["snippet"] = neutral_spec(python, arguments)
        payload["notes"].append("通用格式：按宿主文档把 command/args 映射到其 MCP 服务配置。")

    if args.write and not payload.get("wrote"):
        payload["notes"].append("该宿主或范围不支持自动写入；忽略 --write。")

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="register.py",
        description="生成 nuclear-dev MCP 服务端的注册片段；默认只打印，不修改宿主配置。",
    )
    parser.add_argument("host", choices=HOSTS, help="目标宿主")
    parser.add_argument("--scope", choices=["project", "global"], default="project", help="安装范围")
    parser.add_argument("--project", metavar="路径", help="项目根目录；project 范围必填")
    parser.add_argument(
        "--workspace",
        action="append",
        default=[],
        metavar="路径",
        help="允许 MCP 访问的工作区；可重复；默认使用项目目录",
    )
    parser.add_argument("--allow-write", action="store_true", help="在注册参数中加入 --allow-write")
    parser.add_argument("--python", metavar="解释器", help="启动服务端的 Python；默认当前解释器")
    parser.add_argument("--write", action="store_true", help="仅 Claude Code 项目级：合并写入 .mcp.json")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def print_human(payload: Dict[str, Any]) -> None:
    print("宿主: %s（%s）" % (payload["host_label"], payload["scope"]))
    print("服务端: %s（%s）" % (payload["server_path"], payload["server_source"]))
    print("Python: %s" % payload["python"])
    print("工作区: %s" % ", ".join(payload["workspaces"]))
    print("写入权限: %s" % ("已启用" if payload["allow_write"] else "只读"))
    print("")
    print("注册片段：")
    if payload["format"] == "toml":
        print(payload["snippet"])
    else:
        print(json.dumps(payload["snippet"], ensure_ascii=False, indent=2, sort_keys=True))
    if payload.get("config_path"):
        print("")
        print("配置路径: %s" % payload["config_path"])
    if payload.get("backup"):
        print("已备份: %s" % payload["backup"])
    if payload.get("notes"):
        print("")
        for note in payload["notes"]:
            print("- %s" % note)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = build_payload(args)
    except (RegisterError, OSError) as exc:
        failure = {"ok": False, "status": "error", "host": args.host, "error": str(exc)}
        if args.json:
            emit_json(failure)
        else:
            print("错误: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        emit_json(payload)
    else:
        print_human(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
