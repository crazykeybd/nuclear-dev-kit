#!/usr/bin/env python3
"""MCP 协议的 JSON-RPC 2.0 最小实现（仅标准库）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

JSONRPC_VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002


class RpcError(Exception):
    """可映射为 JSON-RPC 错误对象的失败。"""

    def __init__(self, code: int, message: str, data: Optional[Any] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_error(self, request_id: Optional[Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": self.code, "message": self.message},
        }
        if self.data is not None:
            payload["error"]["data"] = self.data
        return payload


class ToolError(Exception):
    """工具执行失败：映射为 isError=true 的工具结果，不是协议错误。"""


def success(request_id: Optional[Any], result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error(request_id: Optional[Any], code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    return RpcError(code, message, data).to_error(request_id)


def encode(message: Dict[str, Any]) -> bytes:
    text = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def decode(line: bytes) -> Any:
    return json.loads(line.decode("utf-8"))
