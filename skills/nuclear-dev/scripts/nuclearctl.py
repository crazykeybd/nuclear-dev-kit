#!/usr/bin/env python3
"""核能软件开发门禁命令行工具。"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from nuclearlib import (
    STAGE_ARTIFACTS,
    STAGE_LABELS,
    STAGES,
    NuclearError,
    add_evidence,
    build_manifest,
    init_project,
    relative_to_root,
    root_path,
    stage_gate,
    stage_status,
    state_path,
    utc_now,
    validate_project,
)
from nuclearproto import trace as tracing
from nuclearproto.audit import verify as verify_audit

MINIMUM_PYTHON = (3, 7, 3)


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


def record_trace(root: Path, stage: str, include_dependencies: bool, errors: List[str]) -> Dict[str, Any]:
    """写成运行轨迹；写失败只报告，门禁结论与退出码都不变。"""
    try:
        record = tracing.record_gate(
            root,
            stage,
            include_dependencies=include_dependencies,
            errors=errors,
        )
        if record is None:  # 未启用时不会有记录，走不到这里
            return {"ok": False, "error": "轨迹未启用"}
        path = tracing.traces_root(root) / (str(record["trace_id"]) + ".json")
        return {
            "ok": True,
            "trace_id": record["trace_id"],
            "sequence": record["sequence"],
            "record_sha256": record["record_sha256"],
            "path": relative_to_root(root, path),
        }
    except Exception as exc:  # 轨迹是线索不是证据：任何异常都不许改写判定
        print("警告: 门禁判定不变，但运行轨迹未写成: %s" % exc, file=sys.stderr)
        return {"ok": False, "error": str(exc)}


def command_gate(args: argparse.Namespace, root: Path) -> int:
    include_dependencies = not args.no_dependencies
    errors = stage_gate(root, args.stage, include_dependencies=include_dependencies)
    payload = {
        "ok": not errors,
        "command": "gate",
        "root": str(root),
        "stage": args.stage,
        "include_dependencies": include_dependencies,
        "errors": errors,
    }
    if tracing.enabled(bool(getattr(args, "trace", False))):
        payload["trace"] = record_trace(root, args.stage, include_dependencies, errors)
    if args.json:
        emit_json(payload)
    elif errors:
        print("%s门禁阻断，共 %d 项:" % (STAGE_LABELS[args.stage], len(errors)))
        for error in errors:
            print("- %s" % error)
    else:
        print("%s门禁通过。" % STAGE_LABELS[args.stage])
        print("注意：门禁通过只表示已登记证据和人工批准满足规则，不是监管批准。")
    trace = payload.get("trace")
    if trace and not args.json:
        if trace.get("ok"):
            print("运行轨迹: %s（%s）" % (trace["path"], trace["trace_id"]))
        else:
            print("运行轨迹未写成: %s" % trace.get("error"))
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


def _check(identifier: str, ok: bool, errors: Optional[List[str]] = None, **detail: Any) -> Dict[str, Any]:
    return {"id": identifier, "ok": ok, "errors": list(errors or []), "detail": detail}


def command_doctor(args: argparse.Namespace, root: Path) -> int:
    """体检一处工作区：环境、结构、阶段、轨迹链与审计链，一次给结论。

    只读。``ok`` 表示"这处工作区是完好的"——能不能通过某个阶段是另一回事，
    阶段进展只作为事实列出，未开始的阶段不算故障。
    """
    checks = []
    environment = tracing.environment()
    supported = sys.version_info[:3] >= MINIMUM_PYTHON
    checks.append(
        _check(
            "kit",
            supported,
            [] if supported else ["Python %s 低于要求的 %s" % (platform.python_version(), ".".join(str(item) for item in MINIMUM_PYTHON))],
            **environment
        )
    )
    state = state_path(root)
    initialised = (state / "project.json").is_file()
    if initialised:
        workspace_errors = validate_project(root)
        checks.append(_check("workspace", not workspace_errors, workspace_errors, state_dir=str(state)))
        stages = stage_status(root)
    else:
        checks.append(_check("workspace", False, ["未初始化: 缺少 %s；先运行 nuclearctl.py init" % (state / "project.json")], state_dir=str(state)))
        stages = {}
    traces = tracing.verify(root)
    checks.append(
        _check(
            "traces",
            bool(traces["ok"]),
            traces["errors"],
            count=traces["traces"],
            head=traces["head"],
            drift=traces["drift"],
            enabled=tracing.enabled(),
        )
    )
    audit = verify_audit(state / "audit")
    checks.append(_check("audit", bool(audit["ok"]), audit["errors"], records=audit.get("records", 0)))
    ok = all(item["ok"] for item in checks)
    attention = [stage for stage in STAGES if not stages.get(stage, {}).get("passed", False)]
    payload = {
        "ok": ok,
        "command": "doctor",
        "root": str(root),
        "checked_at": utc_now(),
        "environment": environment,
        "checks": checks,
        "stages": [{"stage": stage, "passed": bool(stages.get(stage, {}).get("passed")), "error_count": len(stages.get(stage, {}).get("errors", []))} for stage in STAGES],
        "next": attention[0] if attention else None,
    }
    if args.json:
        emit_json(payload)
    else:
        print("工作区: %s" % root)
        for check in checks:
            print("%-10s %s" % (check["id"], "正常" if check["ok"] else "异常"))
            for error in check["errors"]:
                print("  - %s" % error)
            for drifted in check["detail"].get("drift") or []:
                print(
                    "  * 轨迹 %s 记录的 %s 已%s，请重新运行门禁"
                    % (drifted["trace_id"], drifted["path"], "删除" if drifted["state"] == "removed" else "变更")
                )
        print("阶段进展: %d/%d 通过" % (sum(1 for item in payload["stages"] if item["passed"]), len(STAGES)))
        if payload["next"]:
            print("下一步: 阶段 %s 未通过；运行 gate %s 查看门禁原话。" % (payload["next"], payload["next"]))
        print("体检只读：不写文件、不生成批准；体检通过不等于门禁通过或监管批准。")
    return 0 if ok else 1


def command_trace_list(args: argparse.Namespace, root: Path) -> int:
    records = tracing.list_traces(root, limit=args.limit)
    payload = {"ok": True, "command": "trace list", "root": str(root), "traces": records}
    if args.json:
        emit_json(payload)
    elif not records:
        print("还没有运行轨迹。用 gate <阶段> --trace 记录一次。")
    else:
        for item in records:
            print(
                "%s #%s %s %s %s（%s 项错误，%s 个 span）"
                % (
                    item["trace_id"],
                    item["sequence"],
                    item["kind"],
                    item["stage"] or "-",
                    "通过" if item["ok"] else "阻断",
                    item["error_count"],
                    item["spans"],
                )
            )
    return 0


def command_trace_show(args: argparse.Namespace, root: Path) -> int:
    record = tracing.load_trace(root, args.trace_id)
    payload = {"ok": True, "command": "trace show", "root": str(root), "trace": record}
    if args.json:
        emit_json(payload)
    else:
        verdict = record.get("verdict") or {}
        print("轨迹: %s（序号 %s，%s）" % (record.get("trace_id"), record.get("sequence"), record.get("kind")))
        print("阶段: %s" % (record.get("stage") or "-"))
        print("时间: %s -> %s（%s ms）" % (record.get("started_at"), record.get("finished_at"), record.get("duration_ms")))
        print("结论: %s" % ("通过" if verdict.get("ok") else "阻断"))
        for error in verdict.get("errors") or []:
            print("- %s" % error)
        print("span:")
        for span in record.get("spans") or []:
            print("  %-10s %-24s %s" % (span.get("span_id"), span.get("name"), span.get("status")))
    return 0


def command_trace_verify(args: argparse.Namespace, root: Path) -> int:
    report = tracing.verify(root)
    payload = {"ok": bool(report["ok"]), "command": "trace verify", "root": str(root)}
    payload.update(report)
    if args.json:
        emit_json(payload)
    else:
        print("轨迹数: %d" % report["traces"])
        print("链头: %s" % report["head"])
        if report["ok"]:
            print("轨迹链校验通过。")
        else:
            print("轨迹链校验未通过，共 %d 项:" % len(report["errors"]))
            for error in report["errors"]:
                print("- %s" % error)
        for drifted in report["drift"]:
            print("偏离: %s 记录的 %s 已%s" % (drifted["trace_id"], drifted["path"], "删除" if drifted["state"] == "removed" else "变更"))
    return 0 if report["ok"] else 1


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
    gate_parser.add_argument(
        "--trace",
        action="store_true",
        help="把这次判定写成运行轨迹；环境变量 NUCLEAR_DEV_TRACE=1 也可默认打开",
    )
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

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="体检工作区",
        description="一次检查环境、工作区结构、阶段进展、运行轨迹链与审计链。只读，不写文件。",
    )
    doctor_parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    doctor_parser.set_defaults(handler=command_doctor)

    trace_parser = subparsers.add_parser(
        "trace",
        help="查看与校验运行轨迹",
        description="查看门禁运行轨迹；轨迹是线索不是证据，不参与门禁判定。",
    )
    trace_subparsers = trace_parser.add_subparsers(dest="trace_command", metavar="轨迹子命令")
    trace_list = trace_subparsers.add_parser("list", help="列出轨迹摘要", description="按序号倒序列出轨迹摘要。")
    trace_list.add_argument("--limit", type=int, metavar="条数", help="最多列出多少条")
    trace_list.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    trace_list.set_defaults(handler=command_trace_list)
    trace_show = trace_subparsers.add_parser("show", help="显示一条轨迹", description="按标识显示一条完整轨迹。")
    trace_show.add_argument("trace_id", metavar="轨迹标识", help="例如 TRC-20261107T055404Z-4f3c9a")
    trace_show.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    trace_show.set_defaults(handler=command_trace_show)
    trace_verify = trace_subparsers.add_parser("verify", help="校验轨迹链", description="校验轨迹序号、摘要与前序链接；产物变化单独报告为偏离。")
    trace_verify.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    trace_verify.set_defaults(handler=command_trace_verify)

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
    if args.command == "trace" and not getattr(args, "trace_command", None):
        print("错误: trace 需要子命令 list/show/verify；使用 trace --help 查看帮助。", file=sys.stderr)
        return 2
    root = root_path(args.root)
    try:
        return int(args.handler(args, root))
    except NuclearError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    except tracing.TraceError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("文件操作失败: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
