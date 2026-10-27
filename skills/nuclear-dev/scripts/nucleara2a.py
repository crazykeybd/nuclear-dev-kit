#!/usr/bin/env python3
"""A2A 远程 V&V 客户端命令。

外发是人工动作：授权令牌必须由人在终端里确认生成，C3 原始文件只能从 CLI 发送。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import nuclearlib
from nuclearproto import a2a_client, a2a_export, a2a_policy, a2a_projection, a2a_server, auth
from nuclearproto.a2a_tasks import TaskError, TaskStore
from nuclearproto.audit import AuditError, AuditLog

PROFILE = a2a_client.PROTOCOL_PROFILE


class CliError(Exception):
    """命令参数或前置条件不满足。"""


def emit_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def require_tty(reason: str) -> None:
    # Windows 上 NUL 是字符设备，stdin.isatty() 可能为 True；必须同时检查 stdout。
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise CliError("该操作需要交互终端（%s）；非交互调用一律拒绝" % reason)


def confirm(question: str) -> None:
    require_tty(question)
    print(question)
    try:
        answer = input("输入 yes 确认: ")
    except EOFError:
        raise CliError("未收到确认输入，操作中止")
    if answer.strip() != "yes":
        raise CliError("未确认，操作中止")


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def key_path(args: argparse.Namespace) -> Path:
    value = args.keys or os.environ.get("NUCLEAR_A2A_KEY_FILE")
    if not value:
        raise CliError("缺少密钥文件；使用 --keys 或设置 NUCLEAR_A2A_KEY_FILE")
    return Path(value).expanduser()


def config_path(args: argparse.Namespace) -> Path:
    value = args.config or os.environ.get("NUCLEAR_A2A_CONFIG")
    if not value:
        raise CliError("缺少 A2A 配置；使用 --config 或设置 NUCLEAR_A2A_CONFIG")
    return Path(value).expanduser()


def load_peer_and_store(args: argparse.Namespace):
    config = a2a_client.load_config(config_path(args))
    peer = a2a_client.get_peer(config, args.recipient)
    store = auth.KeyStore(key_path(args))
    store.load()
    if store.agent_id != config["agent"]["agent_id"]:
        raise CliError("密钥文件的 agent_id 与配置不一致")
    return config, peer, store


def command_plan(args: argparse.Namespace) -> Dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    policy = a2a_policy.ExportPolicy.load(project)
    entries: List[Dict[str, str]] = []
    for raw in args.raw or []:
        relative = a2a_policy.normalize_relative(raw)
        policy.assert_raw_exportable(relative, args.recipient)
        path = project / relative
        if not path.is_file():
            raise CliError("原始文件不存在: %s" % relative)
        entries.append({"path": relative, "sha256": sha256_file(path)})
    covered: List[Dict[str, str]] = []
    if entries:
        approvals = a2a_export.load_export_approvals(project, args.recipient, policy)
        covered = a2a_export.cover_raw_entries(entries, approvals)
    out_root = Path(args.out).expanduser().resolve() if args.out else None
    if out_root is not None:
        try:
            out_root.relative_to(project)
        except ValueError:
            raise CliError("--out 必须位于项目目录内")
    result = a2a_projection.build_bundle(
        project,
        args.recipient,
        policy,
        projections=args.projection or None,
        raw_entries=covered,
        out_root=out_root,
    )
    verification = a2a_projection.verify_bundle(result["bundle_dir"])
    return {
        "ok": verification["ok"],
        "command": "plan",
        "project": str(project),
        "recipient": args.recipient,
        "bundle_dir": str(result["bundle_dir"]),
        "bundle_id": result["manifest"]["bundle_id"],
        "digest": result["digest"],
        "projections": [item["name"] for item in result["manifest"]["projections"]],
        "raw_files": [item["path"] for item in result["manifest"]["raw_files"]],
        "errors": verification["errors"],
    }


def command_authorize(args: argparse.Namespace) -> Dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    bundle = Path(args.bundle).expanduser().resolve()
    verification = a2a_projection.verify_bundle(bundle)
    if not verification["ok"]:
        raise CliError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    manifest = verification["manifest"]
    require_tty("生成一次性授权令牌")
    print("即将授权外发：")
    print("  接收方: %s" % manifest.get("recipient", {}).get("agent_id"))
    print("  投影包: %s" % manifest.get("bundle_id"))
    print("  摘要: %s" % verification["digest"])
    print("  文件数: %d" % (len(manifest.get("projections", [])) + len(manifest.get("raw_files", []))))
    if manifest.get("raw_files"):
        print("  ** 包含 C3 原始文件，特批已校验 **")
    confirm("确认生成一次性令牌？")
    ttl = a2a_export.parse_duration(args.ttl)
    record = a2a_export.create_authorization(
        project,
        bundle,
        args.approver,
        ttl_seconds=ttl,
        recipient_name=manifest.get("recipient", {}).get("agent_id"),
    )
    return {
        "ok": True,
        "command": "authorize",
        "token_id": record["token_id"],
        "bundle_digest": record["bundle_digest"],
        "recipient": record["recipient"],
        "max_class": record["max_class"],
        "expires_at": record["expires_at"],
    }


def command_stage(args: argparse.Namespace) -> Dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    config = a2a_client.load_config(config_path(args))
    peer = a2a_client.get_peer(config, args.recipient)
    bundle = Path(args.bundle).expanduser().resolve()
    result = a2a_client.stage_bundle(project, peer, bundle)
    return {"ok": True, "command": "stage", **result}


def command_send(args: argparse.Namespace) -> Dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    bundle = Path(args.bundle).expanduser().resolve()
    config, peer, store = load_peer_and_store(args)
    verification = a2a_projection.verify_bundle(bundle)
    if not verification["ok"]:
        raise CliError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    manifest = verification["manifest"]
    transfer_ref = args.transfer_ref or manifest.get("bundle_id")
    if manifest.get("raw_files"):
        require_tty("发送 C3 原始文件")
        confirm(
            "即将发送 %d 个 C3 原始文件给 %s，确认继续？"
            % (len(manifest["raw_files"]), args.recipient)
        )
    arguments = {
        "recipient": args.recipient,
        "bundle_id": manifest.get("bundle_id"),
        "bundle_digest": verification["digest"],
        "transfer_ref": transfer_ref,
        "files": len(manifest.get("projections", [])) + len(manifest.get("raw_files", [])),
    }
    log = AuditLog(project / ".nuclear-dev" / "audit", actor=config["agent"]["agent_id"])
    try:
        log.append(
            tool="a2a_send",
            workspace=project.name,
            project_path=project.as_posix(),
            arguments=arguments,
            phase="intent",
        )
    except AuditError as exc:
        raise CliError("审计写入失败，发送已中止: %s" % exc)
    try:
        a2a_export.consume_authorization(project, args.token, bundle, args.recipient)
        card = a2a_client.fetch_card(peer, config)
        result = a2a_client.send_task(peer, store, card, bundle, transfer_ref)
    except Exception as exc:
        try:
            log.append(
                tool="a2a_send",
                workspace=project.name,
                project_path=project.as_posix(),
                arguments=arguments,
                phase="result",
                ok=False,
                is_error=True,
            )
        except AuditError:
            pass
        raise
    try:
        log.append(
            tool="a2a_send",
            workspace=project.name,
            project_path=project.as_posix(),
            arguments=arguments,
            phase="result",
            ok=True,
            exit_code=0,
        )
    except AuditError as exc:
        raise CliError("已发送，但结果审计写入失败；请先检查审计日志: %s" % exc)
    return {
        "ok": True,
        "command": "send",
        "recipient": args.recipient,
        "bundle_id": manifest.get("bundle_id"),
        "bundle_digest": verification["digest"],
        "transfer_ref": transfer_ref,
        "task": result.get("task"),
        "card_sha256": result.get("card_sha256"),
        "staged_path": result.get("staged_path"),
    }


def command_status(args: argparse.Namespace) -> Dict[str, Any]:
    config, peer, store = load_peer_and_store(args)
    result = a2a_client.get_task(peer, store, args.task)
    return {"ok": True, "command": "status", "task": result}


def command_cancel(args: argparse.Namespace) -> Dict[str, Any]:
    config, peer, store = load_peer_and_store(args)
    result = a2a_client.cancel_task(peer, store, args.task)
    return {"ok": True, "command": "cancel", "task": result}


def command_serve(args: argparse.Namespace) -> int:
    try:
        project = Path(args.project).expanduser().resolve()
        store = auth.KeyStore(key_path(args))
        store.load()
        agent_id = args.agent_id or store.agent_id
        if agent_id != store.agent_id:
            raise CliError("--agent-id 与密钥文件的 agent_id 不一致")
        config = a2a_server.ServerConfig(
            project=project,
            agent_id=agent_id,
            organization=args.organization,
            spec_revision=args.spec_revision,
            store=store,
            bind=args.bind,
            port=args.port,
            tls_cert=args.tls_cert,
            tls_key=args.tls_key,
            tls_client_ca=args.tls_client_ca,
            trust_proxy_tls=args.trust_proxy_tls,
            transfer_root=args.transfer_root,
            rate_per_minute=args.rate_per_minute,
            rate_burst=args.rate_burst,
        )
        server = a2a_server.create_server(config)
    except (CliError, a2a_server.ServerError, auth.AuthError) as exc:
        payload = {"ok": False, "command": "serve", "status": "error", "error": str(exc)}
        if args.json:
            emit_json(payload)
        else:
            print("错误: %s" % exc, file=sys.stderr)
        return 2
    info = {
        "ok": True,
        "command": "serve",
        "address": server.address[0],
        "port": server.port,
        "agent_id": config.agent_id,
        "organization": config.organization,
        "spec_revision": config.spec_revision,
        "tls": bool(config.tls_cert),
        "proxy_tls": bool(config.trust_proxy_tls),
        "transfer_root": str(config.transfer_root) if config.transfer_root else None,
    }
    if args.json:
        emit_json(info)
    else:
        print("A2A 服务端已启动: http://%s:%d/a2a" % (info["address"], info["port"]))
        print("agent_id: %s" % info["agent_id"])
        print("organization: %s" % info["organization"])
        print("TLS: %s，代理模式: %s" % ("是" if info["tls"] else "否", "是" if info["proxy_tls"] else "否"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("收到中断，正在停止。", file=sys.stderr)
    finally:
        server.shutdown()
    return 0


def command_task_list(args: argparse.Namespace) -> Dict[str, Any]:
    store = TaskStore(Path(args.project).expanduser().resolve())
    tasks = store.list()
    return {
        "ok": True,
        "command": "task-list",
        "count": len(tasks),
        "tasks": [
            {
                "id": item.get("id"),
                "peer": item.get("peer"),
                "state": item.get("state"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "artifacts": len(item.get("artifacts", [])),
            }
            for item in tasks
        ],
    }


def command_task_show(args: argparse.Namespace) -> Dict[str, Any]:
    store = TaskStore(Path(args.project).expanduser().resolve())
    return {"ok": True, "command": "task-show", "task": store.get(args.id)}


def command_task_update(args: argparse.Namespace) -> Dict[str, Any]:
    store = TaskStore(Path(args.project).expanduser().resolve())
    task = store.transition(args.id, args.state, args.note)
    return {"ok": True, "command": "task-update", "task": task}


def command_task_artifact(args: argparse.Namespace) -> Dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    store = TaskStore(project)
    task = store.get(args.id)
    source = Path(args.path).expanduser().resolve()
    if not source.is_file():
        raise CliError("产物文件不存在: %s" % source)
    transfer_root = Path(args.transfer_root).expanduser().resolve()
    if not transfer_root.is_dir():
        raise CliError("transfer_root 不存在: %s" % transfer_root)
    name = source.name
    destination_dir = transfer_root / task["id"]
    destination = destination_dir / name
    if destination.exists():
        raise CliError("产物目标已存在: %s" % destination)
    destination_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    digest = nuclearlib.sha256_file(destination)
    artifact = {
        "name": name,
        "file": name,
        "transferId": "%s/%s" % (task["id"], name),
        "size": destination.stat().st_size,
        "sha256": digest,
        "class": args.classification,
        "created_at": nuclearlib.utc_now(),
    }
    task = store.add_artifact(task["id"], artifact)
    return {"ok": True, "command": "task-artifact", "artifact": artifact, "task": task}


def command_policy_template(_: argparse.Namespace) -> Dict[str, Any]:
    return {
        "ok": True,
        "command": "policy-template",
        "note": "把 recipients 下的内容写入 .nuclear-dev/a2a/export-policy.json；不要直接使用示例组织名。",
        "template": {
            "schema_version": 1,
            "default": "deny",
            "recipients": {
                "<recipient-agent-id>": {
                    "organization": "<对端组织全称>",
                    "max_class": "C2",
                    "projections": ["requirements", "test_summary", "vv_scope"],
                    "allow_c3_raw": False,
                    "scope_label": "<脱敏后的等级标签>",
                }
            },
        },
        "classification_template": {
            "schema_version": 1,
            "entries": [
                {"path": "src/**", "class": "C3", "transferable": True},
                {"path": "<第三方基准题路径>", "class": "C3", "transferable": False},
            ],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nucleara2a.py",
        description="核能软件独立 V&V 的 A2A 客户端。外发需要一次性授权令牌；C3 原始文件仅 CLI 可发。",
    )
    parser.add_argument("--project", default=".", metavar="路径", help="项目根目录，默认当前目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", metavar="子命令")

    plan = sub.add_parser("plan", help="生成 V&V 输入投影包")
    plan.add_argument("--recipient", required=True, metavar="标识", help="策略中的接收方标识")
    plan.add_argument("--projection", action="append", default=[], help="投影名；可重复；默认取策略允许项")
    plan.add_argument("--raw", action="append", default=[], help="需要特批的 C3 项目内相对路径；可重复")
    plan.add_argument("--out", metavar="目录", help="自定义 outbox 目录")
    plan.set_defaults(handler=command_plan)

    authorize = sub.add_parser("authorize", help="生成一次性授权令牌（需要 TTY）")
    authorize.add_argument("--bundle", required=True, metavar="目录", help="投影包目录")
    authorize.add_argument("--approver", required=True, metavar="姓名", help="执行授权的人员")
    authorize.add_argument("--ttl", default="15m", metavar="时长", help="令牌有效期，如 15m、1h；默认 15m")
    authorize.set_defaults(handler=command_authorize)

    stage = sub.add_parser("stage", help="把投影包复制到带外交换目录")
    stage.add_argument("--config", metavar="路径", help="A2A 配置文件")
    stage.add_argument("--recipient", required=True, metavar="标识")
    stage.add_argument("--bundle", required=True, metavar="目录")
    stage.set_defaults(handler=command_stage)

    send = sub.add_parser("send", help="发送委托（需要一次性令牌）")
    send.add_argument("--config", metavar="路径", help="A2A 配置文件")
    send.add_argument("--keys", metavar="路径", help="密钥文件；默认取 NUCLEAR_A2A_KEY_FILE")
    send.add_argument("--recipient", required=True, metavar="标识")
    send.add_argument("--bundle", required=True, metavar="目录")
    send.add_argument("--token", required=True, metavar="令牌", help="authorize 输出的一次性令牌")
    send.add_argument("--transfer-ref", metavar="引用", help="带外引用；默认使用 bundle_id")
    send.set_defaults(handler=command_send)

    status = sub.add_parser("status", help="查询任务状态")
    status.add_argument("--config", metavar="路径")
    status.add_argument("--keys", metavar="路径")
    status.add_argument("--recipient", required=True, metavar="标识")
    status.add_argument("--task", required=True, metavar="任务ID")
    status.set_defaults(handler=command_status)

    cancel = sub.add_parser("cancel", help="取消任务")
    cancel.add_argument("--config", metavar="路径")
    cancel.add_argument("--keys", metavar="路径")
    cancel.add_argument("--recipient", required=True, metavar="标识")
    cancel.add_argument("--task", required=True, metavar="任务ID")
    cancel.set_defaults(handler=command_cancel)

    template = sub.add_parser("policy-template", help="打印导出策略与分类附录模板")
    template.set_defaults(handler=command_policy_template)

    serve = sub.add_parser("serve", help="启动 A2A 服务端（V&V 方）")
    serve.add_argument("--agent-id", metavar="标识", help="本端 agent_id；默认取密钥文件")
    serve.add_argument("--organization", required=True, metavar="组织", help="本端组织全称")
    serve.add_argument("--spec-revision", required=True, metavar="修订", help="锁定的 A2A 规范修订")
    serve.add_argument("--keys", metavar="路径", help="密钥文件；默认取 NUCLEAR_A2A_KEY_FILE")
    serve.add_argument("--bind", default="127.0.0.1", metavar="地址", help="监听地址；默认 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765, metavar="端口", help="监听端口；默认 8765")
    serve.add_argument("--tls-cert", metavar="路径", help="直接 TLS 证书")
    serve.add_argument("--tls-key", metavar="路径", help="直接 TLS 私钥")
    serve.add_argument("--tls-client-ca", metavar="路径", help="启用 mTLS 的客户端 CA")
    serve.add_argument("--trust-proxy-tls", action="store_true", help="反向代理终止 TLS")
    serve.add_argument("--transfer-root", metavar="目录", help="带外交换目录")
    serve.add_argument("--rate-per-minute", type=int, default=10, metavar="次数", help="每对端每分钟请求数")
    serve.add_argument("--rate-burst", type=int, default=20, metavar="次数", help="每对端突发上限")
    serve.set_defaults(handler=command_serve)

    task = sub.add_parser("task", help="服务端任务账本操作")
    task_sub = task.add_subparsers(dest="task_command", metavar="任务子命令")
    task_list = task_sub.add_parser("list", help="列出任务")
    task_list.set_defaults(handler=command_task_list)
    task_show = task_sub.add_parser("show", help="查看任务详情")
    task_show.add_argument("--id", required=True, metavar="任务ID")
    task_show.set_defaults(handler=command_task_show)
    task_update = task_sub.add_parser("update", help="更新任务状态")
    task_update.add_argument("--id", required=True, metavar="任务ID")
    task_update.add_argument("--state", required=True, choices=["working", "input-required", "completed", "failed", "canceled"])
    task_update.add_argument("--note", metavar="备注")
    task_update.set_defaults(handler=command_task_update)
    task_artifact = task_sub.add_parser("artifact", help="登记并暂存任务产物")
    task_artifact.add_argument("--id", required=True, metavar="任务ID")
    task_artifact.add_argument("--path", required=True, metavar="文件")
    task_artifact.add_argument("--classification", choices=["C2", "C3"], default="C2")
    task_artifact.add_argument("--transfer-root", required=True, metavar="目录")
    task_artifact.set_defaults(handler=command_task_artifact)
    return parser


def print_human(payload: Dict[str, Any]) -> None:
    command = payload.get("command")
    if command == "plan":
        print("投影包: %s" % payload["bundle_dir"])
        print("摘要: %s" % payload["digest"])
        print("投影: %s" % ", ".join(payload["projections"]))
        print("C3 原始文件: %s" % (", ".join(payload["raw_files"]) or "无"))
        if not payload["ok"]:
            for error in payload["errors"]:
                print("- %s" % error)
    elif command == "authorize":
        print("一次性令牌: %s" % payload["token_id"])
        print("有效期至: %s" % payload["expires_at"])
        print("分类上限: %s" % payload["max_class"])
    elif command == "stage":
        print("已暂存到: %s" % payload["path"])
        print("transfer_ref: %s" % payload["transfer_ref"])
    elif command == "send":
        task = payload.get("task") or {}
        print("已提交任务: %s" % task.get("id"))
        print("bundle: %s" % payload["bundle_id"])
        print("transfer_ref: %s" % payload["transfer_ref"])
    elif command in ("status", "cancel"):
        task = payload.get("task") or {}
        state = task.get("status", {}).get("state") if isinstance(task.get("status"), dict) else None
        print("任务: %s 状态: %s" % (task.get("id"), state))
    elif command == "policy-template":
        print(payload["note"])
        print(json.dumps(payload["template"], ensure_ascii=False, indent=2))
    elif command == "task-list":
        print("任务数: %d" % payload["count"])
        for item in payload["tasks"]:
            print("- %s %s %s" % (item["id"], item["peer"], item["state"]))
    elif command == "task-show":
        task = payload["task"]
        print("任务: %s" % task["id"])
        print("对端: %s" % task["peer"])
        print("状态: %s" % task["state"])
        print("产物数: %d" % len(task.get("artifacts", [])))
    elif command == "task-update":
        task = payload["task"]
        print("任务: %s 状态: %s" % (task["id"], task["state"]))
    elif command == "task-artifact":
        artifact = payload["artifact"]
        print("产物: %s" % artifact["transferId"])
        print("SHA256: %s" % artifact["sha256"])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    if args.command == "task" and not getattr(args, "task_command", None):
        print("错误: task 需要子命令 list/show/update/artifact。", file=sys.stderr)
        return 2
    if args.command == "serve":
        return args.handler(args)
    try:
        payload = args.handler(args)
    except (CliError, a2a_policy.PolicyError, a2a_projection.ProjectionError, a2a_export.ExportError,
            a2a_client.ClientError, auth.AuthError, AuditError, TaskError,
            a2a_server.ServerError) as exc:
        payload = {"ok": False, "command": args.command, "status": "error", "error": str(exc)}
        if args.json:
            emit_json(payload)
        else:
            print("错误: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        emit_json(payload)
    else:
        print_human(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
