#!/usr/bin/env python3
"""A2A 请求签名与密钥管理（RFC 9421 子集，HMAC-SHA256）。

本模块只依赖标准库。签名保证请求完整性与防重放，不提供不可否认性。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1
CLOCK_SKEW_SECONDS = 300
NONCE_TTL_SECONDS = 600
NONCE_LIMIT = 10000
KEY_STATUSES = ("current", "next", "retiring")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
COMPONENTS = '("@method" "@path" "content-digest")'
ALGORITHM = "hmac-sha256"


class AuthError(Exception):
    """签名、密钥或时钟校验失败。"""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except Exception as exc:
        raise AuthError("base64 解码失败") from exc


def content_digest(body: bytes) -> str:
    return "sha-256=:%s:" % _b64(hashlib.sha256(body).digest())


def signature_params(created: int, nonce: str, keyid: str) -> str:
    return '%s;created=%d;nonce="%s";keyid="%s";alg="%s"' % (COMPONENTS, created, nonce, keyid, ALGORITHM)


def signature_base(method: str, path: str, digest: str, params: str) -> bytes:
    lines = [
        '"@method": ' + method.upper(),
        '"@path": ' + path,
        '"content-digest": ' + digest,
        '"@signature-params": ' + params,
    ]
    return "\n".join(lines).encode("utf-8")


def sign_request(
    secret: bytes,
    keyid: str,
    method: str,
    path: str,
    body: bytes,
    created: Optional[int] = None,
    nonce: Optional[str] = None,
) -> Dict[str, str]:
    created = int(time.time()) if created is None else int(created)
    nonce = nonce or _b64(os.urandom(16)).rstrip("=")
    digest = content_digest(body)
    params = signature_params(created, nonce, keyid)
    signature = hmac.new(secret, signature_base(method, path, digest, params), hashlib.sha256).digest()
    return {
        "Content-Digest": digest,
        "Signature-Input": "sig1=" + params,
        "Signature": "sig1=:%s:" % _b64(signature),
    }


_PARAM_RE = re.compile(r'(\w+)=("([^"]*)"|[^;]+)')
_INPUT_RE = re.compile(r'^sig1=\((?P<components>[^)]*)\);(?P<params>.+)$')


def parse_signature_input(value: str) -> Tuple[str, Dict[str, str]]:
    stripped = value.strip()
    match = _INPUT_RE.match(stripped)
    if not match:
        raise AuthError("Signature-Input 格式无效")
    components = match.group("components").strip()
    if components != '"@method" "@path" "content-digest"':
        raise AuthError("签名覆盖的组件不符合约定")
    params: Dict[str, str] = {}
    for fragment in match.group("params").split(";"):
        fragment = fragment.strip()
        if not fragment or "=" not in fragment:
            continue
        name, raw = fragment.split("=", 1)
        params[name.strip()] = raw.strip().strip('"')
    full = stripped[len("sig1=") :]
    return full, params


def parse_signature(value: str) -> str:
    match = re.match(r"^sig1=:([^:]+):$", value.strip())
    if not match:
        raise AuthError("Signature 格式无效")
    return match.group(1)


class NonceCache:
    def __init__(self, ttl: int = NONCE_TTL_SECONDS, limit: int = NONCE_LIMIT) -> None:
        self.ttl = ttl
        self.limit = limit
        self._entries: Dict[Tuple[str, str], float] = {}

    def check_and_store(self, keyid: str, nonce: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        expired = [key for key, deadline in self._entries.items() if deadline <= now]
        for key in expired:
            self._entries.pop(key, None)
        key = (keyid, nonce)
        if key in self._entries:
            return False
        if len(self._entries) >= self.limit:
            oldest = min(self._entries, key=lambda item: self._entries[item])
            self._entries.pop(oldest, None)
        self._entries[key] = now + self.ttl
        return True


class KeyStore:
    """密钥文件：current / next / retiring 双钥轮换。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._mtime: Optional[int] = None
        self._data: Optional[Dict[str, Any]] = None

    def _check_permissions(self) -> None:
        if os.name == "nt":
            return
        mode = stat.S_IMODE(os.stat(str(self.path)).st_mode)
        if mode & 0o077:
            raise AuthError("密钥文件权限过宽（要求 0600）: %s" % self.path)

    def load(self) -> Dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except OSError as exc:
            raise AuthError("无法读取密钥文件: %s" % exc)
        except ValueError as exc:
            raise AuthError("密钥文件不是有效 JSON: %s" % exc)
        self._check_permissions()
        self._data = self._validate(data)
        self._mtime = self.path.stat().st_mtime_ns
        return self._data

    def _validate(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise AuthError("密钥文件必须是 JSON 对象")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise AuthError("密钥文件 schema_version 必须为 %d" % SCHEMA_VERSION)
        agent_id = data.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise AuthError("密钥文件缺少 agent_id")
        allowed = data.get("allowed_peers")
        if not isinstance(allowed, list) or not allowed or not all(
            isinstance(item, str) and item.strip() for item in allowed
        ):
            raise AuthError("allowed_peers 必须是非空字符串数组")
        keys = data.get("keys")
        if not isinstance(keys, list) or not keys:
            raise AuthError("keys 必须是非空数组")
        seen = set()
        normalized: List[Dict[str, Any]] = []
        for entry in keys:
            if not isinstance(entry, dict):
                raise AuthError("keys 条目必须是对象")
            keyid = entry.get("keyid")
            if not isinstance(keyid, str) or not KEY_ID_RE.match(keyid):
                raise AuthError("keyid 格式无效: %s" % keyid)
            if keyid in seen:
                raise AuthError("keyid 重复: %s" % keyid)
            seen.add(keyid)
            peer = entry.get("peer")
            if peer not in allowed:
                raise AuthError("密钥 %s 的 peer 不在 allowed_peers 中" % keyid)
            status = entry.get("status")
            if status not in KEY_STATUSES:
                raise AuthError("密钥 %s 的 status 无效" % keyid)
            secret = entry.get("secret")
            if not isinstance(secret, str):
                raise AuthError("密钥 %s 缺少 secret" % keyid)
            raw = _unb64(secret)
            if len(raw) < 32:
                raise AuthError("密钥 %s 少于 32 字节" % keyid)
            not_after = entry.get("not_after")
            if not_after is not None:
                if not isinstance(not_after, str):
                    raise AuthError("密钥 %s 的 not_after 无效" % keyid)
                try:
                    from datetime import datetime

                    datetime.fromisoformat(not_after.replace("Z", "+00:00"))
                except ValueError:
                    raise AuthError("密钥 %s 的 not_after 不是 ISO 时间" % keyid)
            normalized.append(
                {
                    "keyid": keyid,
                    "peer": peer,
                    "status": status,
                    "secret": raw,
                    "not_after": not_after,
                }
            )
        data["keys"] = normalized
        for peer in allowed:
            usable = [entry for entry in normalized if entry["peer"] == peer]
            if not usable:
                raise AuthError("allowed_peers 中的 %s 没有任何密钥" % peer)
        return data

    def maybe_reload(self) -> Dict[str, Any]:
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError as exc:
            raise AuthError("无法读取密钥文件: %s" % exc)
        if self._data is None or mtime != self._mtime:
            return self.load()
        return self._data

    @property
    def agent_id(self) -> str:
        return self.maybe_reload()["agent_id"]

    @property
    def allowed_peers(self) -> List[str]:
        return list(self.maybe_reload()["allowed_peers"])

    def signing_key(self, peer: str) -> Dict[str, Any]:
        data = self.maybe_reload()
        if peer not in data["allowed_peers"]:
            raise AuthError("peer 不在 allowed_peers 中: %s" % peer)
        candidates = [
            entry
            for entry in data["keys"]
            if entry["peer"] == peer and entry["status"] == "current" and not _expired(entry)
        ]
        if not candidates:
            raise AuthError("peer %s 没有可用的 current 密钥" % peer)
        return candidates[0]

    def verification_keys(self, peer: Optional[str] = None) -> List[Dict[str, Any]]:
        data = self.maybe_reload()
        return [
            entry
            for entry in data["keys"]
            if (peer is None or entry["peer"] == peer) and not _expired(entry)
        ]

    def key_by_id(self, keyid: str) -> Dict[str, Any]:
        for entry in self.maybe_reload()["keys"]:
            if entry["keyid"] == keyid:
                if _expired(entry):
                    raise AuthError("密钥已过期: %s" % keyid)
                return entry
        raise AuthError("未知 keyid: %s" % keyid)


def _expired(entry: Dict[str, Any]) -> bool:
    value = entry.get("not_after")
    if not value:
        return False
    from datetime import datetime, timezone

    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= datetime.now(timezone.utc)


def verify_request(
    headers: Dict[str, str],
    method: str,
    path: str,
    body: bytes,
    store: KeyStore,
    nonces: NonceCache,
) -> Dict[str, Any]:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    digest_header = normalized.get("content-digest")
    signature_input = normalized.get("signature-input")
    signature_header = normalized.get("signature")
    if not digest_header or not signature_input or not signature_header:
        raise AuthError("缺少签名头")
    if digest_header != content_digest(body):
        raise AuthError("请求体摘要不匹配")
    params_text, params = parse_signature_input(signature_input)
    if params.get("alg") != ALGORITHM:
        raise AuthError("不支持的签名算法")
    keyid = params.get("keyid")
    nonce = params.get("nonce")
    created_raw = params.get("created")
    if not keyid or not nonce or created_raw is None:
        raise AuthError("签名参数不完整")
    try:
        created = int(created_raw)
    except ValueError:
        raise AuthError("created 不是整数")
    now = int(time.time())
    if abs(now - created) > CLOCK_SKEW_SECONDS:
        raise AuthError("请求时间超出允许窗口")
    entry = store.key_by_id(keyid)
    signature = _unb64(parse_signature(signature_header))
    expected = hmac.new(
        entry["secret"], signature_base(method, path, digest_header, params_text), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise AuthError("签名不匹配")
    if not nonces.check_and_store(keyid, nonce):
        raise AuthError("nonce 已使用")
    return {
        "keyid": keyid,
        "peer": entry["peer"],
        "created": created,
        "nonce": nonce,
    }
