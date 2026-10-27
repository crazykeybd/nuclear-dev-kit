#!/usr/bin/env python3
"""A2A 客户端：agent card 校验、带外包暂存、HMAC 签名请求。"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import auth
from .a2a_projection import verify_bundle

SCHEMA_VERSION = 1
PROTOCOL_PROFILE = "nuclear-a2a/1"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CARD_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 30
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


class ClientError(Exception):
    """配置、传输或协议错误。"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_loopback(url: urllib.parse.ParseResult) -> bool:
    return url.hostname in LOOPBACK_HOSTS


def load_config(path: Path) -> Dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ClientError("无法读取 A2A 配置: %s" % exc)
    if not isinstance(data, dict):
        raise ClientError("A2A 配置必须是 JSON 对象")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ClientError("A2A 配置 schema_version 必须为 %d" % SCHEMA_VERSION)
    agent = data.get("agent")
    if not isinstance(agent, dict):
        raise ClientError("A2A 配置缺少 agent")
    for key in ("agent_id", "organization", "spec_revision"):
        value = agent.get(key)
        if not isinstance(value, str) or not value.strip() or value.strip() == "unpinned":
            raise ClientError("agent.%s 必须是非空值，且不能是 unpinned" % key)
    if agent.get("protocol_profile", PROTOCOL_PROFILE) != PROTOCOL_PROFILE:
        raise ClientError("不支持的 protocol_profile: %s" % agent.get("protocol_profile"))
    peers = data.get("peers")
    if not isinstance(peers, dict) or not peers:
        raise ClientError("A2A 配置必须至少包含一个 peer")
    for name, peer in peers.items():
        _validate_peer(name, peer)
        if peer["organization"].strip() == agent["organization"].strip():
            raise ClientError(
                "peer %s 的组织与开发组织相同，不能作为独立 V&V 方" % name
            )
    return data


def _validate_peer(name: str, peer: Any) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ClientError("peer 名称无效")
    if not isinstance(peer, dict):
        raise ClientError("peer %s 必须是对象" % name)
    for key in ("agent_id", "organization", "endpoint"):
        value = peer.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ClientError("peer %s 缺少 %s" % (name, key))
    endpoint = urllib.parse.urlparse(peer["endpoint"])
    if endpoint.scheme not in ("http", "https"):
        raise ClientError("peer %s 的 endpoint 必须是 http(s)" % name)
    if endpoint.scheme == "http" and not _is_loopback(endpoint):
        raise ClientError("peer %s 的明文 http 只允许 loopback" % name)
    if endpoint.username or endpoint.password:
        raise ClientError("peer %s 的 endpoint 不得包含凭据" % name)
    if endpoint.query or endpoint.fragment:
        raise ClientError("peer %s 的 endpoint 不得包含查询或片段" % name)
    ca_file = peer.get("ca_file")
    if ca_file is not None:
        if not isinstance(ca_file, str) or not Path(ca_file).is_file():
            raise ClientError("peer %s 的 ca_file 不存在" % name)
    transfer_root = peer.get("transfer_root")
    if transfer_root is not None and not isinstance(transfer_root, str):
        raise ClientError("peer %s 的 transfer_root 必须是字符串" % name)


def get_peer(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    peers = config.get("peers", {})
    if name not in peers:
        raise ClientError("未知 peer: %s" % name)
    return peers[name]


def _ssl_context(peer: Dict[str, Any]) -> ssl.SSLContext:
    ca_file = peer.get("ca_file")
    return ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()


def _read_limited(response: Any, limit: int, label: str) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ClientError("%s 超过大小上限" % label)
    return data


def _card_url(peer: Dict[str, Any]) -> str:
    if peer.get("card_url"):
        return peer["card_url"]
    endpoint = urllib.parse.urlparse(peer["endpoint"])
    return "%s://%s/.well-known/agent-card.json" % (endpoint.scheme, endpoint.netloc)


def fetch_card(peer: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    url = _card_url(peer)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "http" and not _is_loopback(parsed):
        raise ClientError("agent card 的明文 http 只允许 loopback")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_ssl_context(peer)) as response:
            data = _read_limited(response, MAX_CARD_BYTES, "agent card")
    except urllib.error.HTTPError as exc:
        raise ClientError("获取 agent card 失败: HTTP %s" % exc.code)
    except Exception as exc:
        raise ClientError("获取 agent card 失败: %s" % exc)
    try:
        card = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ClientError("agent card 不是有效 JSON: %s" % exc)
    _validate_card(card, peer, config)
    return {"card": card, "sha256": _sha256_bytes(data), "url": url}


def _validate_card(card: Any, peer: Dict[str, Any], config: Dict[str, Any]) -> None:
    if not isinstance(card, dict):
        raise ClientError("agent card 必须是 JSON 对象")
    if card.get("schema_version") != SCHEMA_VERSION:
        raise ClientError("agent card schema_version 不匹配")
    if card.get("agent_id") != peer["agent_id"]:
        raise ClientError("agent card 的 agent_id 与配置不一致")
    if card.get("organization") != peer["organization"]:
        raise ClientError("agent card 的 organization 与配置不一致")
    if card.get("protocol_profile") != PROTOCOL_PROFILE:
        raise ClientError("agent card 的 protocol_profile 不匹配")
    expected_revision = config["agent"]["spec_revision"]
    if card.get("spec_revision") != expected_revision:
        raise ClientError("agent card 的 spec_revision 不匹配")
    capabilities = card.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise ClientError("agent card 的 capabilities 无效")
    if capabilities.get("streaming") is not False:
        raise ClientError("本实现不支持 streaming，对端必须声明 false")
    if capabilities.get("pushNotifications") is not False:
        raise ClientError("本实现不支持 push notifications，对端必须声明 false")
    security = card.get("security")
    if security is not None:
        if not isinstance(security, dict) or security.get("scheme") != "hmac-sha256":
            raise ClientError("对端安全方案不是 hmac-sha256")


def stage_bundle(project: Path, peer: Dict[str, Any], bundle_dir: Path) -> Dict[str, Any]:
    transfer_root = peer.get("transfer_root")
    if not transfer_root:
        raise ClientError("peer 未配置 transfer_root，无法暂存带外包")
    root = Path(transfer_root).expanduser().resolve()
    project = Path(project).resolve()
    try:
        root.relative_to(project)
    except ValueError:
        pass
    else:
        raise ClientError("transfer_root 不得位于项目目录内")
    root.mkdir(parents=True, exist_ok=True)
    verification = verify_bundle(bundle_dir)
    if not verification["ok"]:
        raise ClientError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    bundle_id = verification["manifest"]["bundle_id"]
    destination = root / bundle_id
    if destination.exists():
        raise ClientError("带外目标已存在: %s" % destination)
    shutil.copytree(str(bundle_dir), str(destination))
    copied = verify_bundle(destination)
    if not copied["ok"]:
        shutil.rmtree(str(destination), ignore_errors=True)
        raise ClientError("暂存后校验失败:\n" + "\n".join("- " + item for item in copied["errors"]))
    return {
        "transfer_ref": bundle_id,
        "path": str(destination),
        "digest": copied["digest"],
    }


def verify_staged(peer: Dict[str, Any], transfer_ref: str, expected_digest: str) -> Path:
    root = peer.get("transfer_root")
    if not root:
        raise ClientError("peer 未配置 transfer_root")
    if not isinstance(transfer_ref, str) or not transfer_ref.strip():
        raise ClientError("transfer_ref 无效")
    if "/" in transfer_ref or "\\" in transfer_ref or ".." in transfer_ref:
        raise ClientError("transfer_ref 不得包含路径分隔符")
    path = Path(root).expanduser().resolve() / transfer_ref
    if not path.is_dir():
        raise ClientError("带外包不存在: %s" % path)
    verification = verify_bundle(path)
    if not verification["ok"]:
        raise ClientError("带外包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    if verification["digest"] != expected_digest:
        raise ClientError("带外包摘要与本地投影包不一致")
    return path


def _endpoint(peer: Dict[str, Any]) -> Tuple[str, str]:
    parsed = urllib.parse.urlparse(peer["endpoint"])
    path = parsed.path or "/"
    return peer["endpoint"], path


def _signed_post(peer: Dict[str, Any], store: auth.KeyStore, payload: Dict[str, Any]) -> Dict[str, Any]:
    endpoint, path = _endpoint(peer)
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_RESPONSE_BYTES:
        raise ClientError("请求体超过 4 MiB 上限")
    key = store.signing_key(peer["agent_id"])
    headers = auth.sign_request(key["secret"], key["keyid"], "POST", path, body)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_ssl_context(peer)) as response:
            data = _read_limited(response, MAX_RESPONSE_BYTES, "响应")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(4096).decode("utf-8", "replace")
        except Exception:
            detail = ""
        finally:
            exc.close()
        if exc.code == 401:
            raise ClientError("对端拒绝认证（401）")
        raise ClientError("对端返回 HTTP %s: %s" % (exc.code, detail))
    except Exception as exc:
        raise ClientError("请求失败: %s" % exc)
    try:
        message = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ClientError("响应不是有效 JSON: %s" % exc)
    if not isinstance(message, dict):
        raise ClientError("响应不是 JSON-RPC 对象")
    if message.get("error"):
        error = message["error"]
        raise ClientError(
            "对端返回错误 %s: %s"
            % (error.get("code") if isinstance(error, dict) else "?", error.get("message") if isinstance(error, dict) else error)
        )
    result = message.get("result")
    if result is None:
        raise ClientError("响应缺少 result")
    return result


def build_message(manifest: Dict[str, Any], transfer_ref: str, spec_revision: Optional[str] = None) -> Dict[str, Any]:
    parts: List[Dict[str, Any]] = [
        {
            "kind": "text",
            "text": "核能软件独立 V&V 委托。投影包摘要: %s" % manifest.get("digest"),
        },
        {
            "kind": "data",
            "data": {
                "bundle_id": manifest.get("bundle_id"),
                "bundle_digest": manifest.get("digest"),
                "recipient": manifest.get("recipient"),
                "projections": [item.get("name") for item in manifest.get("projections", [])],
                "raw_file_count": len(manifest.get("raw_files", [])),
            },
        },
    ]
    for item in list(manifest.get("projections", [])) + list(manifest.get("raw_files", [])):
        parts.append(
            {
                "kind": "file",
                "file": {
                    "name": item.get("file"),
                    "size": item.get("size"),
                    "sha256": item.get("sha256"),
                    "transferId": "%s/%s" % (transfer_ref, item.get("file")),
                    "class": item.get("class"),
                },
            }
        )
    return {
        "message": {"role": "user", "parts": parts},
        "metadata": {
            "protocol_profile": PROTOCOL_PROFILE,
            "spec_revision": spec_revision or "",
            "transfer_ref": transfer_ref,
        },
    }


def send_task(
    peer: Dict[str, Any],
    store: auth.KeyStore,
    card: Dict[str, Any],
    bundle_dir: Path,
    transfer_ref: str,
) -> Dict[str, Any]:
    verification = verify_bundle(bundle_dir)
    if not verification["ok"]:
        raise ClientError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    manifest = verification["manifest"]
    staged = verify_staged(peer, transfer_ref, verification["digest"])
    spec_revision = card.get("card", {}).get("spec_revision") if isinstance(card, dict) else None
    params = build_message(manifest, transfer_ref, spec_revision)
    payload = {
        "jsonrpc": "2.0",
        "id": secrets.token_hex(8),
        "method": "message/send",
        "params": params,
    }
    result = _signed_post(peer, store, payload)
    return {
        "task": result,
        "bundle_digest": verification["digest"],
        "transfer_ref": transfer_ref,
        "staged_path": str(staged),
        "card_sha256": card.get("sha256"),
    }


def get_task(peer: Dict[str, Any], store: auth.KeyStore, task_id: str) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": secrets.token_hex(8),
        "method": "tasks/get",
        "params": {"id": task_id},
    }
    return _signed_post(peer, store, payload)


def cancel_task(peer: Dict[str, Any], store: auth.KeyStore, task_id: str) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": secrets.token_hex(8),
        "method": "tasks/cancel",
        "params": {"id": task_id},
    }
    return _signed_post(peer, store, payload)
