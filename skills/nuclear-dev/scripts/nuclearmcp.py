#!/usr/bin/env python3
"""nuclear-dev-bot 的 MCP stdio 服务端。

只暴露确定性判定与只读资源；不存在 approve 工具，也不写任何文件。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from nuclearproto import McpServer, WorkspaceError, WorkspaceSet, build_surface
from nuclearproto import a2a_client, auth
from nuclearproto.audit import AuditError, build_sinks
from nuclearproto.jsonrpc import INTERNAL_ERROR, PARSE_ERROR, encode, error
from nuclearproto.surface import KIT_VERSION, SCHEMA_VERSION

SERVER_NAME = "nuclear-dev-bot"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nuclearmcp.py",
        description=(
            "核能软件开发门禁的 MCP stdio 服务端。\n"
            "只提供判定与只读资源；不生成批准，也不写项目文件。"
        ),
    )
    parser.add_argument(
        "--workspace",
        action="append",
        default=[],
        metavar="路径",
        help="允许访问的工作区根目录；可重复。调用方只能传其内的相对路径。",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="传输方式；当前仅支持 stdio",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="启用写入工具（初始化、证据登记、发布清单）；默认只读。写入仍不包含批准。",
    )
    parser.add_argument(
        "--audit-sink",
        action="append",
        default=[],
        metavar="路径或URL",
        help="审计外部出口；可重复。文件路径不得位于 workspace 内；URL 仅支持 https（或 loopback http）。",
    )
    parser.add_argument(
        "--audit-sink-token-file",
        metavar="路径",
        help="HTTPS 审计出口的 Bearer 令牌文件；不接受命令行明文。",
    )
    parser.add_argument("--a2a-config", metavar="路径", help="A2A 对端配置；启用 nuclear_a2a_send")
    parser.add_argument("--a2a-keys", metavar="路径", help="A2A 密钥文件；与 --a2a-config 同时使用")
    return parser


def serve_stdio(server: McpServer, stdin: BinaryIO, stdout: BinaryIO) -> int:
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            stdout.write(encode(error(None, PARSE_ERROR, "无法解析 JSON-RPC 消息")))
            stdout.flush()
            continue
        response = server.handle(message)
        if response is not None:
            try:
                encoded = encode(response)
            except (TypeError, ValueError):
                encoded = encode(error(None, INTERNAL_ERROR, "响应无法序列化为 JSON"))
            stdout.write(encoded)
            stdout.flush()
    return 0


def build_server(
    workspaces: WorkspaceSet,
    allow_write: bool = False,
    audit_sinks: Optional[List[Dict[str, Any]]] = None,
    audit_context: Optional[Dict[str, Any]] = None,
    a2a_context: Optional[Dict[str, Any]] = None,
) -> McpServer:
    surface = build_surface(
        workspaces,
        allow_write=allow_write,
        audit_sinks=audit_sinks,
        audit_context=audit_context,
        a2a_context=a2a_context,
    )
    return McpServer(
        name=SERVER_NAME,
        version=KIT_VERSION,
        instructions=surface["instructions"],
        tools=surface["tools"],
        resources=surface["resources"],
        templates=surface["templates"],
        prompts=surface["prompts"],
        prompt_loader=surface["prompt_loader"],
        resource_loader=surface["resource_loader"],
        audit_context=surface["audit_context"],
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspaces = WorkspaceSet(args.workspace)
        sinks = build_sinks(args.audit_sink, args.audit_sink_token_file, workspaces.roots())
    except WorkspaceError as exc:
        sys.stderr.write("错误: %s\n" % exc)
        return 2
    except AuditError as exc:
        sys.stderr.write("错误: %s\n" % exc)
        return 2

    a2a_context = None
    if args.a2a_config or args.a2a_keys:
        if not args.allow_write:
            sys.stderr.write("错误: --a2a-config/--a2a-keys 需要与 --allow-write 一起使用\n")
            return 2
        if not (args.a2a_config and args.a2a_keys):
            sys.stderr.write("错误: --a2a-config 与 --a2a-keys 必须同时提供\n")
            return 2
        try:
            config = a2a_client.load_config(Path(args.a2a_config))
            store = auth.KeyStore(Path(args.a2a_keys))
            store.load()
            if store.agent_id != config["agent"]["agent_id"]:
                raise auth.AuthError("密钥文件的 agent_id 与 A2A 配置不一致")
        except (a2a_client.ClientError, auth.AuthError) as exc:
            sys.stderr.write("错误: %s\n" % exc)
            return 2
        a2a_context = {"config": config, "store": store}

    server = build_server(
        workspaces,
        allow_write=args.allow_write,
        audit_sinks=sinks,
        audit_context={"client": "unknown"},
        a2a_context=a2a_context,
    )
    sys.stderr.write(
        "nuclear-dev-bot MCP 已启动：version=%s schema_version=%s write=%s workspaces=%s\n"
        % (
            KIT_VERSION,
            SCHEMA_VERSION,
            "on" if args.allow_write else "off",
            ",".join(workspaces.ids()),
        )
    )
    sys.stderr.flush()
    return serve_stdio(server, sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    sys.exit(main())
