#!/usr/bin/env python3
"""核能软件开发门禁命令行工具。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from nuclearlib import (
    STAGE_ARTIFACTS,
    STAGE_LABELS,
    STAGES,
    NuclearError,
    add_evidence,
    build_manifest,
    init_project,
    root_path,
    stage_gate,
    stage_status,
    validate_project,
)


class ChineseHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """把 argparse 的通用帮助标题转换为中文。"""

    _translations = {
        "usage:": "用法:",
        "positional arguments:": "位置参数:",
        "optional arguments:": "可选参数:",
        "options:": "可选参数:",
        "show this help message and exit": "显示此帮助信息并退出",
        "positional arguments": "位置参数",
        "optional arguments": "可选参数",
    }

    def _translate(self, text):
        if text is None:
            return None
        for source, target in self._translations.items():
            text = text.replace(source, target)
        return text

    def add_text(self, text):
        translated = self._translate(text)
        if translated in ("位置参数", "可选参数"):
            translated += ":"
        return super().add_text(translated)

    def add_usage(self, usage, actions, groups, prefix=None):
        if prefix is None:
            prefix = "用法: "
        return super().add_usage(usage, actions, groups, prefix=prefix)

    def start_section(self, heading):
        return super().start_section(self._translate(heading))

    def add_argument(self, action):
        if action.help:
            action.help = self._translate(action.help)
        return super().add_argument(action)


class ChineseArgumentParser(argparse.ArgumentParser):
    """把 argparse 的常见错误与帮助标题转换为中文。"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", ChineseHelpFormatter)
        super().__init__(*args, **kwargs)

    def add_subparsers(self, **kwargs):
        kwargs.setdefault("parser_class", ChineseArgumentParser)
        return super().add_subparsers(**kwargs)

    def error(self, message: str) -> None:
        translations = {
            "the following arguments are required": "缺少必需参数",
            "invalid choice": "无效选项",
            "unrecognized arguments": "无法识别的参数",
            "argument": "参数",
        }
        translated = message
        for source, target in translations.items():
            translated = translated.replace(source, target)
        self.print_usage(sys.stderr)
        self.exit(2, "%s: 错误: %s\n" % (self.prog, translated))


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def command_init(args: argparse.Namespace, root: Path) -> int:
    project = init_project(root, name=args.name, project_id=args.project_id)
    payload = {"ok": True, "command": "init", "root": str(root), "project": project}
    if args.json:
        emit_json(payload)
    else:
        print("已初始化核能软件开发工作区: %s" % root)
        print("项目标识: %s" % project["project_id"])
        print("下一步: 使用 nuclear-plan 编写策划产物并登记证据。")
    return 0


def command_status(args: argparse.Namespace, root: Path) -> int:
    status = stage_status(root)
    payload = {"ok": True, "command": "status", "root": str(root), "stages": status}
    if args.json:
        emit_json(payload)
    else:
        print("工作区: %s" % root)
        for stage in STAGES:
            record = status[stage]
            marker = "通过" if record["passed"] else "阻断"
            print("%-14s %-4s %s" % (stage, marker, STAGE_LABELS[stage]))
            for error in record["errors"]:
                print("  - %s" % error)
    return 0


def command_validate(args: argparse.Namespace, root: Path) -> int:
    errors = validate_project(root)
    payload = {
        "ok": not errors,
        "command": "validate",
        "root": str(root),
        "errors": errors,
        "checked_artifacts": [STAGE_ARTIFACTS[stage] for stage in STAGES],
    }
    if args.json:
        emit_json(payload)
    elif errors:
        print("工作区校验未通过，共 %d 项:" % len(errors))
        for error in errors:
            print("- %s" % error)
    else:
        print("工作区结构、证据哈希与已登记批准校验通过。")
    return 0 if not errors else 1


def command_gate(args: argparse.Namespace, root: Path) -> int:
    errors = stage_gate(root, args.stage, include_dependencies=not args.no_dependencies)
    payload = {
        "ok": not errors,
        "command": "gate",
        "root": str(root),
        "stage": args.stage,
        "include_dependencies": not args.no_dependencies,
        "errors": errors,
    }
    if args.json:
        emit_json(payload)
    elif errors:
        print("%s门禁阻断，共 %d 项:" % (STAGE_LABELS[args.stage], len(errors)))
        for error in errors:
            print("- %s" % error)
    else:
        print("%s门禁通过。" % STAGE_LABELS[args.stage])
        print("注意：门禁通过只表示已登记证据和人工批准满足规则，不是监管批准。")
    return 0 if not errors else 1


def command_evidence_add(args: argparse.Namespace, root: Path) -> int:
    record = add_evidence(
        root,
        source=args.path,
        kind=args.kind,
        producer=args.producer,
        command=args.command,
        result=args.result,
        captured_at=args.captured_at,
    )
    payload = {"ok": True, "command": "evidence-add", "root": str(root), "evidence": record}
    if args.json:
        emit_json(payload)
    else:
        print("已登记证据 %s" % record["id"])
        print("文件: %s" % record["path"])
        print("SHA256: %s" % record["sha256"])
        print("结果: %s" % record["result"])
    return 0


def command_manifest(args: argparse.Namespace, root: Path) -> int:
    destination, manifest = build_manifest(root, args.version, force=args.force)
    payload = {
        "ok": True,
        "command": "manifest",
        "root": str(root),
        "path": str(destination),
        "manifest": manifest,
    }
    if args.json:
        emit_json(payload)
    else:
        print("已生成软件配置清单: %s" % destination)
        print("软件版本: %s" % args.version)
        print("受控文件数: %d" % len(manifest.get("files", [])))
    return 0


def build_parser() -> ChineseArgumentParser:
    parser = ChineseArgumentParser(
        prog="nuclearctl.py",
        description="核能数值软件七阶段研发门禁工具。本工具不会代替人工批准或监管判断。",
        epilog=(
            "阶段顺序: plan -> requirements -> design -> implementation -> test -> vv -> release\n"
            "安全边界: 不存在 approve 子命令；人工批准文件必须由具备权限的人独立编写和签署。"
        ),
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="路径",
        help="核能软件项目根目录，默认为当前目录",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="子命令")

    init_parser = subparsers.add_parser("init", help="初始化项目工作区", description="初始化项目工作区。")
    init_parser.add_argument("--name", metavar="名称", help="项目显示名称")
    init_parser.add_argument("--id", dest="project_id", metavar="标识", help="小写项目标识")
    init_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    init_parser.set_defaults(handler=command_init)

    status_parser = subparsers.add_parser("status", help="查看各阶段状态", description="查看各阶段状态；不递归检查前置阶段。")
    status_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    status_parser.set_defaults(handler=command_status)

    validate_parser = subparsers.add_parser("validate", help="校验工作区", description="校验项目结构、产物、证据哈希和已登记批准。")
    validate_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    validate_parser.set_defaults(handler=command_validate)

    gate_parser = subparsers.add_parser("gate", help="执行阶段门禁", description="执行阶段门禁；默认递归检查全部前置阶段。")
    gate_parser.add_argument("stage", choices=STAGES, metavar="阶段", help="阶段名: " + ", ".join(STAGES))
    gate_parser.add_argument("--no-dependencies", action="store_true", help="仅检查当前阶段，不递归检查前置阶段")
    gate_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    gate_parser.set_defaults(handler=command_gate)

    evidence_parser = subparsers.add_parser("evidence", help="管理证据索引", description="管理证据索引；证据必须位于项目目录内。")
    evidence_subparsers = evidence_parser.add_subparsers(dest="evidence_command", metavar="证据子命令")
    evidence_add = evidence_subparsers.add_parser("add", help="登记一个实际证据文件", description="计算 SHA256 并登记证据文件。")
    evidence_add.add_argument("path", metavar="证据路径", help="项目内的证据文件路径")
    evidence_add.add_argument("--kind", required=True, metavar="类型", help="证据类型，例如 test-log")
    evidence_add.add_argument("--producer", required=True, metavar="生产者", help="证据生产者姓名或组织")
    evidence_add.add_argument("--command", required=True, metavar="命令", help="产生证据的命令或操作说明")
    evidence_add.add_argument(
        "--result",
        required=True,
        choices=["passed", "failed", "observed", "not_applicable"],
        help="证据结果",
    )
    evidence_add.add_argument("--captured-at", metavar="日期时间", help="ISO-8601 采集时间；默认当前 UTC 时间")
    evidence_add.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    evidence_add.set_defaults(handler=command_evidence_add)

    manifest_parser = subparsers.add_parser("manifest", help="生成软件配置清单", description="发布门禁通过后生成确定性的软件配置清单。")
    manifest_parser.add_argument("--version", required=True, metavar="版本", help="语义版本，例如 1.0.0")
    manifest_parser.add_argument("--force", action="store_true", help="覆盖内容不同的同名清单")
    manifest_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    manifest_parser.set_defaults(handler=command_manifest)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    if args.command == "evidence" and not getattr(args, "evidence_command", None):
        print("错误: evidence 需要子命令 add；使用 evidence --help 查看帮助。", file=sys.stderr)
        return 2
    root = root_path(args.root)
    try:
        return int(args.handler(args, root))
    except NuclearError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("文件操作失败: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
