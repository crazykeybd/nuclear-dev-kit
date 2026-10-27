#!/usr/bin/env python3
"""nuclear-dev-kit 便捷安装入口：检测宿主、预览、安装、初始化并验证。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_DIR.parent
INSTALLER = SKILLS_ROOT / "nuclear-setup" / "scripts" / "install.py"
NUCLEARCTL = SKILLS_ROOT / "nuclear-dev" / "scripts" / "nuclearctl.py"
HOSTS = ["claude", "codex", "opencode", "reasonix", "generic"]
HOST_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "opencode",
    "reasonix": "Reasonix",
    "generic": "通用 Agent",
    "all": "全部宿主",
}


class QuickInstallError(Exception):
    """便捷安装参数、依赖脚本或子进程输出失败。"""


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


def run_python(script: Path, argv: Sequence[str]) -> Tuple[int, str, str]:
    """用当前解释器调用同包脚本，确保跨平台和 UTF-8 输出。"""
    if not script.is_file():
        raise QuickInstallError("缺少同包脚本: %s" % script)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(script)] + list(argv),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return completed.returncode, completed.stdout, completed.stderr


def parse_last_json(text: str) -> Optional[Dict[str, Any]]:
    """解析脚本输出：先整体解析，再退回最后一整行 JSON 对象。

    同包脚本输出格式不同——install.py 输出单行紧凑 JSON，
    nuclearctl.py 输出带缩进的多行 JSON——两种都要支持。
    """
    stripped = text.strip()
    if stripped:
        try:
            value = json.loads(stripped)
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
    for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def reasonix_home() -> Path:
    """Reasonix 的 home：REASONIX_HOME > Windows %APPDATA%/reasonix > ~/.reasonix。"""
    value = os.environ.get("REASONIX_HOME")
    if value:
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (Path(appdata) / "reasonix").resolve()
        return (Path.home() / "AppData" / "Roaming" / "reasonix").resolve()
    return (Path.home() / ".reasonix").resolve()


def host_marker_candidates(project: Path, scope: str) -> List[Tuple[str, Path, str]]:
    home = Path.home()
    if scope == "project":
        primary = [
            ("claude", project / ".claude", "项目中的 .claude 目录"),
            ("codex", project / ".agents", "项目中的 .agents 目录"),
            ("opencode", project / ".opencode", "项目中的 .opencode 目录"),
            ("reasonix", project / ".reasonix", "项目中的 .reasonix 目录"),
        ]
        secondary = [
            ("claude", home / ".claude", "本机 ~/.claude 目录"),
            ("codex", home / ".codex", "本机 ~/.codex 目录"),
            ("opencode", home / ".config" / "opencode", "本机 ~/.config/opencode 目录"),
            ("reasonix", home / ".reasonix", "本机 ~/.reasonix 目录"),
        ]
    else:
        primary = [
            ("claude", home / ".claude", "本机 ~/.claude 目录"),
            ("codex", home / ".codex", "本机 ~/.codex 目录"),
            ("opencode", home / ".config" / "opencode", "本机 ~/.config/opencode 目录"),
            ("reasonix", reasonix_home(), "本机 Reasonix home 目录"),
            ("generic", home / ".agents", "本机 ~/.agents 目录"),
        ]
        secondary = [
            ("claude", project / ".claude", "项目中的 .claude 目录"),
            ("codex", project / ".agents", "项目中的 .agents 目录"),
            ("opencode", project / ".opencode", "项目中的 .opencode 目录"),
            ("reasonix", project / ".reasonix", "项目中的 .reasonix 目录"),
        ]
    return primary + secondary


def detect_hosts(project: Path, scope: str) -> Tuple[List[str], str]:
    """按环境变量、宿主目录的顺序检测可用宿主，返回优先级列表和首个依据。"""
    found: List[str] = []
    reasons: List[str] = []

    def add(host: str, reason: str) -> None:
        if host not in found:
            found.append(host)
            reasons.append(reason)

    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        add("claude", "检测到 Claude Code 会话环境变量")
    if os.environ.get("CODEX_HOME"):
        add("codex", "检测到 CODEX_HOME")
    if os.environ.get("REASONIX_HOME"):
        add("reasonix", "检测到 REASONIX_HOME")
    for host, marker, reason in host_marker_candidates(project, scope):
        if marker.is_dir() or marker.is_file():
            add(host, "检测到" + reason)
    return found, (reasons[0] if reasons else "未检测到任何宿主标记")


def normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_parser() -> ChineseArgumentParser:
    parser = ChineseArgumentParser(
        prog="quickinstall.py",
        description="一条命令安装 nuclear-dev-kit：自动检测宿主，预览后写入，可顺带初始化和验证。",
        epilog=(
            "安全边界: 默认 dry-run；只有 --yes 且未指定 --dry-run 才写入。\n"
            "安装器不修改宿主配置、项目源码或批准文件，也永远不会生成批准。"
        ),
        formatter_class=ChineseHelpFormatter,
    )
    parser.add_argument("host", nargs="?", default="auto", choices=HOSTS + ["all", "auto"], help="目标宿主；auto 表示自动检测")
    parser.add_argument("--host", dest="host_option", choices=HOSTS + ["all", "auto"], help="目标宿主的可选写法，与位置参数等价")
    parser.add_argument("--scope", choices=["project", "global"], default="global", help="安装范围")
    parser.add_argument("--project", metavar="路径", default=".", help="项目根目录；project 范围必填，初始化时也使用该目录")
    parser.add_argument("--init", action="store_true", help="安装后在项目内初始化 .nuclear-dev 工作区")
    parser.add_argument("--name", metavar="名称", help="初始化时的项目名称；默认取项目目录名")
    parser.add_argument("--id", metavar="标识", help="初始化时的小写项目标识；默认由名称推导")
    parser.add_argument("--verify", action="store_true", help="安装或初始化后运行 status 与 gate plan 做真实检查")
    parser.add_argument("--dry-run", action="store_true", help="只预检并输出计划，不写入文件")
    parser.add_argument("--yes", action="store_true", help="确认执行写入")
    parser.add_argument("--force", action="store_true", help="允许备份并覆盖已存在的同名 Skill")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def failure(status: str, message: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    payload["ok"] = False
    payload["status"] = status
    payload["error"] = message
    return 2, payload


def install_skills(host: str, args: argparse.Namespace, project: Path, confirmed: bool) -> Tuple[int, Dict[str, Any], str]:
    argv = [host, "--scope", args.scope, "--json"]
    if args.scope == "project":
        argv += ["--project", str(project)]
    if args.force:
        argv.append("--force")
    if confirmed:
        argv.append("--yes")
    else:
        argv.append("--dry-run")
    code, stdout, stderr = run_python(INSTALLER, argv)
    parsed = parse_last_json(stdout)
    if parsed is None:
        return 2, {"ok": False, "status": "error", "error": "安装器未返回 JSON"}, (stderr or stdout).strip()
    return code, parsed, ""


def initialize_workspace(args: argparse.Namespace, project: Path) -> Dict[str, Any]:
    display_name = (args.name or project.name or "nuclear-software").strip() or "nuclear-software"
    requested_id = (args.id or display_name).strip()
    project_id = normalize_id(requested_id) or "nuclear-software"
    record: Dict[str, Any] = {
        "root": str(project),
        "name": display_name,
        "id": project_id,
        "status": "planned",
        "ok": True,
    }
    if args.id and project_id != args.id:
        record["id_normalized_from"] = args.id
    code, stdout, stderr = run_python(
        NUCLEARCTL,
        ["--root", str(project), "init", "--name", display_name, "--id", project_id, "--json"],
    )
    parsed = parse_last_json(stdout)
    detail = (stderr or stdout).strip()
    if code == 0 and parsed is not None:
        record["status"] = "initialized"
        record["project"] = parsed.get("project")
        return record
    if code == 2 and "已初始化" in (stderr + stdout):
        record["status"] = "already_initialized"
        record["ok"] = True
        record["note"] = "工作区已存在，未重复初始化；使用 status 与 validate 检查。"
        return record
    record["ok"] = False
    record["status"] = "failed"
    record["exit_code"] = code
    record["error"] = detail or "初始化失败"
    return record


def verify_workspace(project: Path) -> Dict[str, Any]:
    initialized = (project / ".nuclear-dev" / "project.json").is_file()
    status_code, status_out, status_err = run_python(
        NUCLEARCTL, ["--root", str(project), "status", "--json"]
    )
    gate_code, gate_out, gate_err = run_python(
        NUCLEARCTL, ["--root", str(project), "gate", "plan", "--json"]
    )
    status_payload = parse_last_json(status_out)
    gate_payload = parse_last_json(gate_out)
    return {
        "ok": status_payload is not None and gate_payload is not None,
        "initialized": initialized,
        "status_exit": status_code,
        "gate_plan_exit": gate_code,
        "status": status_payload,
        "gate_plan": gate_payload,
        "status_error": (status_err or "").strip() or None,
        "gate_plan_error": (gate_err or "").strip() or None,
        "note": (
            "全新项目的 gate plan 返回 1 属预期；门禁通过不代表监管批准。"
            if initialized
            else "项目尚未初始化，验证结果只说明 CLI 可执行；需要时加 --init。"
        ),
    }


def execute(args: argparse.Namespace) -> Tuple[int, Dict[str, Any]]:
    project = Path(args.project).expanduser().resolve()
    confirmed = bool(args.yes) and not args.dry_run
    payload: Dict[str, Any] = {
        "ok": False,
        "dry_run": not confirmed,
        "host": None,
        "host_source": None,
        "detected_hosts": [],
        "scope": args.scope,
        "project": str(project),
        "install": None,
        "init": None,
        "verify": None,
        "next_steps": [],
    }
    if not INSTALLER.is_file():
        return failure("missing_installer", "未找到同包安装器: %s" % INSTALLER, payload)
    if not NUCLEARCTL.is_file():
        return failure("missing_cli", "未找到门禁 CLI: %s" % NUCLEARCTL, payload)
    if (args.scope == "project" or args.init) and not project.is_dir():
        return failure("missing_project", "项目目录不存在: %s" % project, payload)

    host = args.host_option or args.host
    if args.host_option and args.host not in ("auto", args.host_option):
        return failure(
            "conflicting_host",
            "位置参数 %s 与 --host %s 冲突，请只保留一种写法。" % (args.host, args.host_option),
            payload,
        )
    if host == "auto":
        detected, reason = detect_hosts(project, args.scope)
        payload["detected_hosts"] = detected
        if not detected:
            return failure(
                "needs_host",
                "未检测到宿主，请使用 --host 指定：" + "、".join(HOSTS + ["all"]),
                payload,
            )
        host = detected[0]
        payload["host_source"] = reason
    else:
        payload["host_source"] = "用户指定"
    payload["host"] = host

    install_code, install_payload, install_detail = install_skills(host, args, project, confirmed)
    payload["install"] = install_payload
    if install_code != 0:
        payload["ok"] = False
        payload["status"] = install_payload.get("status", "error")
        conflicts = install_payload.get("conflicts") or []
        failures = install_payload.get("failures") or []
        if conflicts:
            payload["error"] = "目标已存在；确认覆盖后加 --force（安装器会先备份）。"
        elif failures:
            payload["failures"] = failures
            payload["error"] = "部分宿主安装失败：%s" % "、".join(item["host"] for item in failures)
        else:
            payload["error"] = install_payload.get("error") or install_detail or "安装失败"
        return install_code, payload

    payload["ok"] = True
    payload["status"] = install_payload.get("status", "planned" if not confirmed else "installed")
    targets = install_payload.get("targets") or []
    host_count = max(1, len(install_payload.get("hosts") or [host]))
    payload["target_count"] = len(targets)
    payload["skill_count"] = len(targets) // host_count

    if args.init:
        if not confirmed:
            payload["init"] = {"ok": True, "status": "planned", "root": str(project), "dry_run": True}
        else:
            payload["init"] = initialize_workspace(args, project)
            if not payload["init"].get("ok"):
                payload["ok"] = False
                payload["status"] = "init_failed"
                payload["error"] = payload["init"].get("error")

    if args.verify:
        if not confirmed:
            payload["verify"] = {"ok": True, "status": "planned", "dry_run": True}
        elif not project.is_dir():
            payload["verify"] = {"ok": False, "error": "项目目录不存在"}
        else:
            payload["verify"] = verify_workspace(project)

    if not confirmed:
        payload["next_steps"] = [
            "检查 targets 与 conflicts；确认无误后追加 --yes 执行写入。",
            "写入后新开一个宿主会话，让 Skill 目录重新扫描。",
        ]
    else:
        payload["next_steps"] = [
            "新开一个宿主会话，确认 %s 中出现 %d 个 nuclear-* Skill。" % (HOST_LABELS.get(host, host), payload["skill_count"]),
            "进入目标项目运行 status --json，再用 nuclear-plan 开始第一阶段。",
        ]
        if not args.init:
            payload["next_steps"].insert(0, "项目尚未初始化；需要时运行 --init 或在项目内调用 nuclear-setup。")

    return (0 if payload["ok"] else 1), payload

def group_targets(targets: Sequence[Dict[str, Any]]) -> List[Tuple[str, List[str]]]:
    grouped: Dict[str, List[str]] = {}
    for target in targets:
        root = str(Path(target["destination"]).parent)
        grouped.setdefault(root, []).append(target["name"])
    return [(root, names) for root, names in grouped.items()]


def print_human(payload: Dict[str, Any]) -> None:
    print("状态: %s" % payload.get("status", "error"))
    if payload.get("host"):
        print("宿主: %s（%s）" % (HOST_LABELS.get(payload["host"], payload["host"]), payload.get("host_source") or "未知依据"))
    else:
        print("宿主: 未确定")
    print("范围: %s" % (payload.get("scope") or "-"))
    if payload.get("detected_hosts"):
        print("检测到的宿主: %s" % ", ".join(payload["detected_hosts"]))
    install = payload.get("install") or {}
    targets = install.get("targets") or []
    print("目标 Skill 数: %d" % len(targets))
    for root, names in group_targets(targets):
        print("  %s" % root)
        print("    %s" % ", ".join(names))
    conflicts = install.get("conflicts") or []
    if conflicts:
        print("冲突:")
        for item in conflicts:
            print("- %s" % item)
    if payload.get("init"):
        init = payload["init"]
        print("初始化: %s（%s）" % (init.get("status"), init.get("root")))
    if payload.get("verify"):
        verify = payload["verify"]
        if verify.get("status") == "planned":
            print("验证: 计划中（dry-run）")
        else:
            print("验证: status 退出码 %s，gate plan 退出码 %s" % (verify.get("status_exit"), verify.get("gate_plan_exit")))
            print("  %s" % verify.get("note", ""))
    if payload.get("error"):
        print("错误: %s" % payload["error"])
    if payload.get("next_steps"):
        print("下一步:")
        for index, step in enumerate(payload["next_steps"], 1):
            print("%d) %s" % (index, step))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, payload = execute(args)
    except QuickInstallError as exc:
        payload = {
            "ok": False,
            "dry_run": bool(getattr(args, "dry_run", False) or not getattr(args, "yes", False)),
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
