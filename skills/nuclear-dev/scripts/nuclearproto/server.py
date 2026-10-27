#!/usr/bin/env python3
"""MCP 服务端骨架：方法分发、工具 / 资源 / 提示词注册。"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Sequence

from .jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RESOURCE_NOT_FOUND,
    RpcError,
    ToolError,
    error,
    success,
)

DEFAULT_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


class McpServer:
    def __init__(
        self,
        name: str,
        version: str,
        instructions: str,
        tools: Sequence[Dict[str, Any]],
        resources: Sequence[Dict[str, Any]],
        templates: Sequence[Dict[str, Any]],
        prompts: Sequence[Dict[str, Any]],
        prompt_loader: Callable[[str], str],
        resource_loader: Callable[[str], Dict[str, Any]],
        audit_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        self._audit_context = audit_context if audit_context is not None else {}
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        for item in tools:
            tool_name = item["name"]
            self._handlers[tool_name] = item["handler"]
            self._tools[tool_name] = {key: value for key, value in item.items() if key != "handler"}
        self._resources = list(resources)
        self._templates = list(templates)
        self._prompts = {item["name"]: item for item in prompts}
        self._load_prompt = prompt_loader
        self._load_resource = resource_loader

    # --- 分发 -----------------------------------------------------

    def handle(self, message: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(message, dict):
            return error(None, INVALID_REQUEST, "请求必须是 JSON 对象")
        if "id" not in message:
            self._dispatch_safely(message, notification=True)
            return None
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return error(request_id, INVALID_REQUEST, "缺少 method")
        try:
            result = self._dispatch(method, message.get("params") or {})
        except RpcError as exc:
            return exc.to_error(request_id)
        except Exception as exc:  # 兜底：不让单个请求打断服务
            return error(request_id, INTERNAL_ERROR, "内部错误: %s" % exc)
        return success(request_id, result)

    def _dispatch_safely(self, message: Dict[str, Any], notification: bool) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            return
        try:
            self._dispatch(method, message.get("params") or {})
        except Exception:
            return

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Any:
        if not isinstance(params, dict):
            raise RpcError(INVALID_PARAMS, "params 必须是对象")
        if method == "initialize":
            return self._initialize(params)
        if method in ("notifications/initialized", "notifications/cancelled"):
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": list(self._tools.values())}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": self._resources}
        if method == "resources/templates/list":
            return {"resourceTemplates": self._templates}
        if method == "resources/read":
            return self._read_resource(params)
        if method == "prompts/list":
            return {"prompts": list(self._prompts.values())}
        if method == "prompts/get":
            return self._get_prompt(params)
        raise RpcError(METHOD_NOT_FOUND, "未知方法: %s" % method)

    # --- 具体方法 -------------------------------------------------

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        client_info = params.get("clientInfo")
        if isinstance(client_info, dict):
            client_name = client_info.get("name")
            if isinstance(client_name, str) and client_name.strip():
                self._audit_context["client"] = client_name.strip()
        requested = params.get("protocolVersion")
        protocol = requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
        return {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": self.name, "version": self.version},
            "instructions": self.instructions,
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise RpcError(INVALID_PARAMS, "缺少工具名 name")
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS, "arguments 必须是对象")
        tool = self._tools.get(name)
        if tool is None:
            raise RpcError(INVALID_PARAMS, "未知工具: %s" % name)
        try:
            payload = self._handlers[name](arguments)
        except ToolError as exc:
            return self._tool_result({"ok": False, "error": str(exc)}, is_error=True)
        except RpcError:
            raise
        except Exception as exc:
            return self._tool_result({"ok": False, "error": "工具执行失败: %s" % exc}, is_error=True)
        is_error = bool(payload.pop("_is_error", False)) if isinstance(payload, dict) else False
        return self._tool_result(payload, is_error=is_error)

    def _tool_result(self, payload: Any, is_error: bool) -> Dict[str, Any]:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        result: Dict[str, Any] = {"content": [{"type": "text", "text": text}]}
        if is_error:
            result["isError"] = True
        return result

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise RpcError(INVALID_PARAMS, "缺少 uri")
        loaded = self._load_resource(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": loaded["mimeType"],
                    "text": loaded["text"],
                }
            ]
        }

    def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise RpcError(INVALID_PARAMS, "缺少提示词名 name")
        prompt = self._prompts.get(name)
        if prompt is None:
            raise RpcError(INVALID_PARAMS, "未知提示词: %s" % name)
        text = self._load_prompt(name)
        return {
            "description": prompt.get("description", ""),
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }


def parse_error_response() -> Dict[str, Any]:
    return error(None, PARSE_ERROR, "无法解析 JSON-RPC 消息")


def resource_not_found(uri: str) -> RpcError:
    return RpcError(RESOURCE_NOT_FOUND, "资源不存在: %s" % uri)
