#!/usr/bin/env python3
"""A2A 服务端：agent card、HMAC 认证、任务状态机与入站隔离。

只读判定不在这里：服务端只接收委托、记录任务与校验带外文件。
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import auth
from .a2a_client import PROTOCOL_PROFILE
from .a2a_tasks import TaskError, TaskStore, public_task
from .audit import AuditError, AuditLog, warn

SCHEMA_VERSION = 1
RPC_PARSE_ERROR = -32700
RPC_INVALID_REQUEST = -32600
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603
RPC_TASK_NOT_FOUND = -32001
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_PARTS = 100
MAX_TEXT_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_STRING_BYTES = 1024 * 1024
MAX_LIST_ITEMS = 1000
METHODS = ("message/send", "tasks/get", "tasks/cancel")
LOOPBACK_BINDS = ("127.0.0.1", "::1", "localhost")


class ServerError(Exception):
    """启动配置或服务端状态错误。"""


class RpcFailure(Exception):
    def __init__(self, code: int, message: str, http_status: int = 200) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class RateLimiter:
    def __init__(self, per_minute: int, burst: int) -> None:
        self.rate = max(0.0, per_minute / 60.0)
        self.burst = max(1, burst)
        self._state: Dict[str, Tuple[float, float]] = {}

    def allow(self, peer: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        tokens, last = self._state.get(peer, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rate)
        if tokens < 1.0:
            self._state[peer] = (tokens, now)
            return False
        self._state[peer] = (tokens - 1.0, now)
        return True


class ServerConfig:
    def __init__(
        self,
        project: Path,
        agent_id: str,
        organization: str,
        spec_revision: str,
        store: auth.KeyStore,
        bind: str = "127.0.0.1",
        port: int = 0,
        tls_cert: Optional[str] = None,
        tls_key: Optional[str] = None,
        tls_client_ca: Optional[str] = None,
        trust_proxy_tls: bool = False,
        transfer_root: Optional[str] = None,
        rate_per_minute: int = 10,
        rate_burst: int = 20,
        max_body: int = MAX_BODY_BYTES,
    ) -> None:
        self.project = Path(project).resolve()
        self.agent_id = agent_id
        self.organization = organization
        self.spec_revision = spec_revision
        self.store = store
        self.bind = bind
        self.port = port
        self.tls_cert = tls_cert
        self.tls_key = tls_key
        self.tls_client_ca = tls_client_ca
        self.trust_proxy_tls = trust_proxy_tls
        self.transfer_root = Path(transfer_root).resolve() if transfer_root else None
        self.rate_per_minute = rate_per_minute
        self.rate_burst = rate_burst
        self.max_body = max_body
        self.tasks = TaskStore(self.project)
        self.nonces = auth.NonceCache()
        self.limiter = RateLimiter(rate_per_minute, rate_burst)


def validate_config(config: ServerConfig) -> None:
    if not config.project.is_dir():
        raise ServerError("项目目录不存在: %s" % config.project)
    for name in ("agent_id", "organization", "spec_revision"):
        value = getattr(config, name)
        if not isinstance(value, str) or not value.strip() or value.strip() == "unpinned":
            raise ServerError("%s 必须是非空值，且不能是 unpinned" % name)
    loopback = config.bind in LOOPBACK_BINDS
    if not loopback:
        if not (config.tls_cert and config.tls_key):
            raise ServerError("非 loopback 绑定必须提供 --tls-cert 与 --tls-key")
        if config.trust_proxy_tls:
            raise ServerError("--trust-proxy-tls 只适用于 loopback 绑定")
    if bool(config.tls_cert) != bool(config.tls_key):
        raise ServerError("--tls-cert 与 --tls-key 必须同时提供")
    for path in (config.tls_cert, config.tls_key, config.tls_client_ca):
        if path and not Path(path).is_file():
            raise ServerError("TLS 文件不存在: %s" % path)
    if config.transfer_root is not None and not config.transfer_root.is_dir():
        raise ServerError("transfer_root 不存在: %s" % config.transfer_root)
    if config.rate_per_minute <= 0 or config.rate_burst <= 0:
        raise ServerError("限流参数必须为正数")


class _TlsContextProvider:
    def __init__(self, cert: str, key: str, client_ca: Optional[str]) -> None:
        self.cert = Path(cert)
        self.key = Path(key)
        self.client_ca = Path(client_ca) if client_ca else None
        self._context: Optional[ssl.SSLContext] = None
        self._signature: Optional[Tuple[int, int, int]] = None

    def _mtimes(self) -> Tuple[int, int, int]:
        return (
            self.cert.stat().st_mtime_ns,
            self.key.stat().st_mtime_ns,
            self.client_ca.stat().st_mtime_ns if self.client_ca else 0,
        )

    def __call__(self) -> ssl.SSLContext:
        signature = self._mtimes()
        if self._context is not None and signature == self._signature:
            return self._context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(self.cert), str(self.key))
        if self.client_ca is not None:
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(str(self.client_ca))
        self._context = context
        self._signature = signature
        return context


class _HttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: Tuple[str, int],
        handler: Callable[..., BaseHTTPRequestHandler],
        config: ServerConfig,
        context_provider: Optional[_TlsContextProvider] = None,
    ) -> None:
        self.config = config
        self.context_provider = context_provider
        super().__init__(address, handler)

    def get_request(self):
        sock, address = super().get_request()
        if self.context_provider is None:
            return sock, address
        try:
            return self.context_provider().wrap_socket(sock, server_side=True), address
        except Exception:
            sock.close()
            raise


def agent_card(config: ServerConfig) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": config.agent_id,
        "organization": config.organization,
        "protocol_profile": PROTOCOL_PROFILE,
        "spec_revision": config.spec_revision,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "security": {"scheme": "hmac-sha256"},
        "roles": ["vv"],
        "methods": list(METHODS),
    }


def _validate_shape(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise RpcFailure(RPC_INVALID_REQUEST, "JSON 嵌套过深")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise RpcFailure(RPC_INVALID_REQUEST, "JSON 键无效")
            _validate_shape(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise RpcFailure(RPC_INVALID_REQUEST, "数组过长")
        for child in value:
            _validate_shape(child, depth + 1)
    elif isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise RpcFailure(RPC_INVALID_REQUEST, "字符串过长")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nuclear-dev-bot/0.1"

    def log_message(self, *args) -> None:
        return

    @property
    def config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    # --- 响应 ---------------------------------------------------

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _rpc_ok(self, request_id: Any, result: Any) -> None:
        self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _rpc_error(self, request_id: Any, code: int, message: str, http_status: int = 200) -> None:
        self._send_json(
            http_status,
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        )

    # --- 审计 ---------------------------------------------------

    def _audit(
        self,
        peer: str,
        tool: str,
        phase: str,
        arguments: Dict[str, Any],
        ok: Optional[bool] = None,
        is_error: bool = False,
        exit_code: Optional[int] = None,
    ) -> None:
        log = AuditLog(self.config.project / ".nuclear-dev" / "audit", actor=peer or "unknown")
        log.append(
            tool=tool,
            workspace=self.config.project.name,
            project_path=self.config.project.as_posix(),
            arguments=arguments,
            phase=phase,
            ok=ok,
            is_error=is_error,
            exit_code=exit_code,
        )

    def _audit_best_effort(self, peer: str, tool: str, arguments: Dict[str, Any], ok: bool) -> None:
        try:
            self._audit(peer, tool, "result", arguments, ok=ok, is_error=not ok)
        except AuditError as exc:
            warn("审计写入失败（已降级）: %s" % exc)

    # --- HTTP ---------------------------------------------------

    def do_GET(self) -> None:
        if self.path != "/.well-known/agent-card.json":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(200, agent_card(self.config))

    def do_POST(self) -> None:
        config = self.config
        if self.path != "/a2a":
            self._send_json(404, {"error": "not found"})
            return
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            self._send_json(415, {"error": "application/json required"})
            return
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self._send_json(411, {"error": "Content-Length required"})
            return
        try:
            length = int(length_header)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return
        if length < 0 or length > config.max_body:
            self._send_json(413, {"error": "payload too large"})
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self._send_json(400, {"error": "incomplete body"})
            return

        socket_peer = self.client_address[0]
        headers = {key: value for key, value in self.headers.items()}
        try:
            identity = auth.verify_request(
                headers, "POST", self.path, body, config.store, config.nonces
            )
        except auth.AuthError:
            self._audit_best_effort(
                "unknown",
                "a2a_auth",
                {"path": self.path, "socket_peer": socket_peer},
                False,
            )
            self._send_json(401, {"error": "unauthorized"})
            return

        peer = identity["peer"]
        forwarded_identity = None
        if config.trust_proxy_tls:
            if socket_peer not in ("127.0.0.1", "::1"):
                self._send_json(403, {"error": "proxy mode requires loopback peer"})
                return
            if headers.get("X-Forwarded-Proto") != "https":
                self._send_json(400, {"error": "X-Forwarded-Proto must be https"})
                return
            forwarded_identity = headers.get("X-Client-Cert-Subject") or headers.get("X-Forwarded-For")

        if not config.limiter.allow(peer):
            self._audit_best_effort(peer, "a2a_rate_limit", {"socket_peer": socket_peer}, False)
            self._send_json(429, {"error": "rate limited"})
            return

        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._audit_best_effort(peer, "a2a_parse", {"socket_peer": socket_peer}, False)
            self._rpc_error(None, RPC_PARSE_ERROR, "parse error")
            return
        request_id = message.get("id") if isinstance(message, dict) else None
        try:
            _validate_shape(message)
            result = self._dispatch(message, peer, socket_peer, forwarded_identity)
        except RpcFailure as exc:
            self._audit_best_effort(peer, "a2a_reject", {"request_id": request_id}, False)
            self._rpc_error(request_id, exc.code, exc.message, exc.http_status)
            return
        except Exception:
            self._audit_best_effort(peer, "a2a_error", {"request_id": request_id}, False)
            self._rpc_error(request_id, RPC_INTERNAL_ERROR, "internal error")
            return
        self._rpc_ok(request_id, result)

    # --- 分发 ---------------------------------------------------

    def _dispatch(
        self,
        message: Any,
        peer: str,
        socket_peer: str,
        forwarded_identity: Optional[str],
    ) -> Dict[str, Any]:
        if not isinstance(message, dict):
            raise RpcFailure(RPC_INVALID_REQUEST, "请求必须是 JSON 对象")
        if message.get("jsonrpc") != "2.0":
            raise RpcFailure(RPC_INVALID_REQUEST, "jsonrpc 必须为 2.0")
        if message.get("id") is None:
            raise RpcFailure(RPC_INVALID_REQUEST, "缺少 id")
        method = message.get("method")
        if method not in METHODS:
            raise RpcFailure(RPC_METHOD_NOT_FOUND, "未知方法: %s" % method)
        params = message.get("params")
        if not isinstance(params, dict):
            raise RpcFailure(RPC_INVALID_PARAMS, "params 必须是对象")
        base = {"socket_peer": socket_peer, "forwarded_identity": forwarded_identity}
        if method == "message/send":
            return self._message_send(peer, params, base)
        if method == "tasks/get":
            return self._tasks_get(peer, params, base)
        return self._tasks_cancel(peer, params, base)

    def _message_send(self, peer: str, params: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, dict):
            raise RpcFailure(RPC_INVALID_PARAMS, "缺少 message")
        if message.get("role") not in ("user", "agent"):
            raise RpcFailure(RPC_INVALID_PARAMS, "message.role 无效")
        parts = message.get("parts")
        if not isinstance(parts, list) or not parts or len(parts) > MAX_PARTS:
            raise RpcFailure(RPC_INVALID_PARAMS, "parts 数量无效")
        metadata = params.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise RpcFailure(RPC_INVALID_PARAMS, "metadata 必须是对象")
        profile = metadata.get("protocol_profile")
        if profile is not None and profile != PROTOCOL_PROFILE:
            raise RpcFailure(RPC_INVALID_PARAMS, "protocol_profile 不匹配")
        revision = metadata.get("spec_revision")
        if revision and revision != self.config.spec_revision:
            raise RpcFailure(RPC_INVALID_PARAMS, "spec_revision 不匹配")

        files: List[Dict[str, Any]] = []
        for part in parts:
            if not isinstance(part, dict):
                raise RpcFailure(RPC_INVALID_PARAMS, "part 必须是对象")
            kind = part.get("kind")
            if kind == "text":
                text = part.get("text")
                if not isinstance(text, str):
                    raise RpcFailure(RPC_INVALID_PARAMS, "text part 缺少 text")
                if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                    raise RpcFailure(RPC_INVALID_PARAMS, "text part 过长")
            elif kind == "data":
                data = part.get("data")
                if not isinstance(data, dict):
                    raise RpcFailure(RPC_INVALID_PARAMS, "data part 缺少 data")
                if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > MAX_TEXT_BYTES:
                    raise RpcFailure(RPC_INVALID_PARAMS, "data part 过大")
            elif kind == "file":
                files.append(self._verify_file(part.get("file")))
            else:
                raise RpcFailure(RPC_INVALID_PARAMS, "未知 part 类型: %s" % kind)

        arguments = dict(base)
        arguments.update({"method": "message/send", "peer": peer, "parts": len(parts), "files": len(files)})
        try:
            self._audit(peer, "a2a_message_send", "intent", arguments)
        except AuditError as exc:
            raise RpcFailure(RPC_INTERNAL_ERROR, "审计写入失败，请求已拒绝: %s" % exc, http_status=500)
        try:
            task = self.config.tasks.create(
                peer,
                {"message": message, "metadata": metadata},
                files,
            )
        except TaskError as exc:
            self._audit_best_effort(peer, "a2a_message_send", arguments, False)
            raise RpcFailure(RPC_INTERNAL_ERROR, str(exc), http_status=500)
        try:
            self._audit(peer, "a2a_message_send", "result", arguments, ok=True, exit_code=0)
        except AuditError as exc:
            raise RpcFailure(
                RPC_INTERNAL_ERROR,
                "任务 %s 已创建，但结果审计写入失败: %s" % (task["id"], exc),
                http_status=500,
            )
        return {"id": task["id"], "status": {"state": task["state"]}}

    def _verify_file(self, file_obj: Any) -> Dict[str, Any]:
        if not isinstance(file_obj, dict):
            raise RpcFailure(RPC_INVALID_PARAMS, "file part 缺少 file 对象")
        for forbidden in ("bytes", "content", "base64", "inline"):
            if forbidden in file_obj:
                raise RpcFailure(RPC_INVALID_PARAMS, "不允许内联文件字节")
        name = file_obj.get("name")
        transfer_id = file_obj.get("transferId")
        size = file_obj.get("size")
        digest = file_obj.get("sha256")
        if not isinstance(name, str) or not name.strip():
            raise RpcFailure(RPC_INVALID_PARAMS, "file.name 无效")
        if not isinstance(transfer_id, str) or not transfer_id.strip():
            raise RpcFailure(RPC_INVALID_PARAMS, "file.transferId 无效")
        if transfer_id.startswith("/") or "\\" in transfer_id or ".." in transfer_id.split("/"):
            raise RpcFailure(RPC_INVALID_PARAMS, "file.transferId 越界")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise RpcFailure(RPC_INVALID_PARAMS, "file.size 无效")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise RpcFailure(RPC_INVALID_PARAMS, "file.sha256 无效")
        verified = False
        if self.config.transfer_root is not None:
            root = self.config.transfer_root
            path = (root / transfer_id).resolve()
            if not _is_within(root, path):
                raise RpcFailure(RPC_INVALID_PARAMS, "file.transferId 越出 transfer_root")
            if path.is_file():
                if path.stat().st_size != size:
                    raise RpcFailure(RPC_INVALID_PARAMS, "文件大小不符: %s" % transfer_id)
                if _sha256_file(path) != digest:
                    raise RpcFailure(RPC_INVALID_PARAMS, "文件摘要不符: %s" % transfer_id)
                verified = True
        return {
            "name": name,
            "transfer_id": transfer_id,
            "size": size,
            "sha256": digest,
            "verified": verified,
        }

    def _tasks_get(self, peer: str, params: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
        task_id = params.get("id")
        if not isinstance(task_id, str):
            raise RpcFailure(RPC_INVALID_PARAMS, "缺少任务 id")
        arguments = dict(base)
        arguments.update({"method": "tasks/get", "peer": peer, "task_id": task_id})
        try:
            task = self.config.tasks.get_for_peer(task_id, peer)
        except TaskError:
            self._audit_best_effort(peer, "a2a_tasks_get", arguments, False)
            raise RpcFailure(RPC_TASK_NOT_FOUND, "任务不存在")
        try:
            self._audit(peer, "a2a_tasks_get", "result", arguments, ok=True, exit_code=0)
        except AuditError as exc:
            raise RpcFailure(RPC_INTERNAL_ERROR, "审计写入失败: %s" % exc, http_status=500)
        return public_task(task)

    def _tasks_cancel(self, peer: str, params: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
        task_id = params.get("id")
        if not isinstance(task_id, str):
            raise RpcFailure(RPC_INVALID_PARAMS, "缺少任务 id")
        arguments = dict(base)
        arguments.update({"method": "tasks/cancel", "peer": peer, "task_id": task_id})
        try:
            task = self.config.tasks.get_for_peer(task_id, peer)
        except TaskError:
            self._audit_best_effort(peer, "a2a_tasks_cancel", arguments, False)
            raise RpcFailure(RPC_TASK_NOT_FOUND, "任务不存在")
        if task.get("state") in ("completed", "failed", "canceled"):
            return public_task(task)
        try:
            self._audit(peer, "a2a_tasks_cancel", "intent", arguments)
        except AuditError as exc:
            raise RpcFailure(RPC_INTERNAL_ERROR, "审计写入失败: %s" % exc, http_status=500)
        try:
            task = self.config.tasks.transition(task_id, "canceled", "对端请求取消")
        except TaskError as exc:
            self._audit_best_effort(peer, "a2a_tasks_cancel", arguments, False)
            raise RpcFailure(RPC_INTERNAL_ERROR, str(exc))
        try:
            self._audit(peer, "a2a_tasks_cancel", "result", arguments, ok=True, exit_code=0)
        except AuditError as exc:
            raise RpcFailure(RPC_INTERNAL_ERROR, "审计写入失败: %s" % exc, http_status=500)
        return public_task(task)


class A2AServer:
    def __init__(self, httpd: _HttpServer, config: ServerConfig) -> None:
        self.httpd = httpd
        self.config = config
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def address(self) -> Tuple[str, int]:
        return self.httpd.server_address[0], self.httpd.server_address[1]

    def serve_forever(self) -> None:
        self.httpd.serve_forever(poll_interval=0.2)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None


def create_server(config: ServerConfig) -> A2AServer:
    validate_config(config)
    context_provider = None
    if config.tls_cert and config.tls_key:
        context_provider = _TlsContextProvider(config.tls_cert, config.tls_key, config.tls_client_ca)
    httpd = _HttpServer((config.bind, config.port), _Handler, config, context_provider)
    return A2AServer(httpd, config)
