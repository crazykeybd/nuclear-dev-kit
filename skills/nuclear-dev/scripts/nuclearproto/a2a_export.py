#!/usr/bin/env python3
"""C3 导出特批与一次性授权令牌。

特批文件必须由两名不同组织的真实人员签署；本模块只校验与消费，不创建特批。
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import nuclearlib

from .a2a_policy import ExportPolicy, PolicyError, normalize_relative
from .a2a_projection import bundle_digest, verify_bundle
from .audit import file_lock

SCHEMA_VERSION = 1
EXP_ID_RE = re.compile(r"^EXP-[0-9]{3,}$")
TOKEN_ID_RE = re.compile(r"^AUTH-[0-9a-f]{16}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 7 * 86400


class ExportError(Exception):
    """特批、令牌或投影包校验失败。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ExportError("不是 ISO-8601 时间: %s" % value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_duration(value: str) -> int:
    match = re.match(r"^(\d+)([smhd])$", value.strip())
    if not match:
        raise ExportError("时长格式无效，使用如 15m、1h、7d")
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    if seconds <= 0 or seconds > MAX_TTL_SECONDS:
        raise ExportError("时长必须在 1 秒到 7 天之间")
    return seconds


def _sha256_file(path: Path) -> str:
    return nuclearlib.sha256_file(path)


def export_approvals_dir(project: Path) -> Path:
    return project / ".nuclear-dev" / "a2a" / "export-approvals"


def authorizations_dir(project: Path) -> Path:
    return project / ".nuclear-dev" / "a2a" / "authorizations"


def load_export_approvals(project: Path, recipient_name: str, policy: ExportPolicy) -> List[Dict[str, Any]]:
    directory = export_approvals_dir(project)
    if not directory.is_dir():
        return []
    records = []
    for path in sorted(directory.glob("EXP-*.json")):
        try:
            with path.open("r", encoding="utf-8") as stream:
                record = json.load(stream)
        except (OSError, ValueError) as exc:
            raise ExportError("无法读取特批 %s: %s" % (path.name, exc))
        validate_export_record(project, record, recipient_name, policy, source=path.name)
        records.append(record)
    return records


def validate_export_record(
    project: Path,
    record: Any,
    recipient_name: str,
    policy: ExportPolicy,
    source: str = "EXP",
) -> None:
    if not isinstance(record, dict):
        raise ExportError("%s: 必须是 JSON 对象" % source)
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ExportError("%s: schema_version 必须为 %d" % (source, SCHEMA_VERSION))
    identifier = record.get("id")
    if not isinstance(identifier, str) or not EXP_ID_RE.match(identifier):
        raise ExportError("%s: id 格式无效" % source)
    if not isinstance(record.get("purpose"), str) or not record["purpose"].strip():
        raise ExportError("%s: purpose 不能为空" % source)
    if not isinstance(record.get("statement"), str) or not record["statement"].strip():
        raise ExportError("%s: statement 不能为空" % source)
    recipient = record.get("recipient")
    if not isinstance(recipient, dict):
        raise ExportError("%s: 缺少 recipient" % source)
    if recipient.get("agent_id") != recipient_name:
        raise ExportError("%s: 接收方不匹配" % source)
    expected_org = policy.recipient(recipient_name)["organization"]
    if recipient.get("organization") != expected_org:
        raise ExportError("%s: 接收方组织与策略不一致" % source)
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, str):
        raise ExportError("%s: 缺少 expires_at" % source)
    if parse_time(expires_at) <= _now():
        raise ExportError("%s: 已过期" % source)

    files = record.get("files")
    if not isinstance(files, list) or not files:
        raise ExportError("%s: files 必须是非空数组" % source)
    for entry in files:
        if not isinstance(entry, dict):
            raise ExportError("%s: files 条目必须是对象" % source)
        relative = normalize_relative(entry.get("path"))
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            raise ExportError("%s: %s 的 sha256 无效" % (source, relative))
        if entry.get("class") != "C3":
            raise ExportError("%s: %s 必须标记为 C3" % (source, relative))
        try:
            policy.assert_raw_exportable(relative, recipient_name)
        except PolicyError as exc:
            raise ExportError("%s: %s" % (source, exc))
        path = project / relative
        if not path.is_file():
            raise ExportError("%s: 文件不存在 %s" % (source, relative))
        if _sha256_file(path) != digest:
            raise ExportError("%s: 文件哈希不匹配 %s" % (source, relative))

    approvers = record.get("approvers")
    if not isinstance(approvers, list) or len(approvers) < 2:
        raise ExportError("%s: 必须有两名批准人" % source)
    names = set()
    organizations = set()
    for approver in approvers:
        if not isinstance(approver, dict):
            raise ExportError("%s: approvers 条目必须是对象" % source)
        for key in ("name", "role", "organization", "actor_type", "signed_at"):
            value = approver.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ExportError("%s: approver 缺少 %s" % (source, key))
        if approver["actor_type"] != "human":
            raise ExportError("%s: 批准人必须是 human" % source)
        if approver["name"] in names:
            raise ExportError("%s: 批准人姓名重复" % source)
        if approver["organization"] in organizations:
            raise ExportError("%s: 批准人组织必须不同" % source)
        names.add(approver["name"])
        organizations.add(approver["organization"])
        signed_at = parse_time(approver["signed_at"])
        if signed_at > _now() + timedelta(seconds=300):
            raise ExportError("%s: 签署时间在未来" % source)


def cover_raw_entries(
    raw_entries: Sequence[Dict[str, str]],
    approvals: Sequence[Dict[str, Any]],
) -> List[Dict[str, str]]:
    covered: List[Dict[str, str]] = []
    for entry in raw_entries:
        relative = normalize_relative(entry["path"])
        digest = entry["sha256"]
        match = None
        for approval in approvals:
            for item in approval.get("files", []):
                if normalize_relative(item.get("path")) == relative and item.get("sha256") == digest:
                    match = approval
                    break
            if match is not None:
                break
        if match is None:
            raise ExportError("原始文件没有有效的双人特批: %s" % relative)
        covered.append(
            {
                "path": relative,
                "sha256": digest,
                "authorization_id": match["id"],
            }
        )
    return covered


def required_class(manifest: Dict[str, Any]) -> str:
    return "C3" if manifest.get("raw_files") else "C2"


def create_authorization(
    project: Path,
    bundle_dir: Path,
    approver: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    recipient_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(approver, str) or not approver.strip():
        raise ExportError("必须提供 --approver")
    verification = verify_bundle(bundle_dir)
    if not verification["ok"]:
        raise ExportError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    manifest = verification["manifest"]
    digest = verification["digest"]
    recipient = manifest.get("recipient", {}).get("agent_id")
    if recipient_name and recipient_name != recipient:
        raise ExportError("投影包接收方与命令不一致")
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ExportError("TTL 超出允许范围")
    now = _now()
    token_id = "AUTH-" + secrets.token_hex(8)
    record = {
        "schema_version": SCHEMA_VERSION,
        "token_id": token_id,
        "bundle_id": manifest.get("bundle_id"),
        "bundle_digest": digest,
        "recipient": recipient,
        "max_class": required_class(manifest),
        "approver": approver.strip(),
        "issued_at": iso(now),
        "expires_at": iso(now + timedelta(seconds=ttl_seconds)),
        "used_at": None,
    }
    directory = authorizations_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (token_id + ".json")
    if path.exists():
        raise ExportError("令牌 ID 冲突，请重试")
    nuclearlib.atomic_write_json(path, record)
    return record


def consume_authorization(
    project: Path,
    token_id: str,
    bundle_dir: Path,
    recipient_name: str,
) -> Dict[str, Any]:
    if not isinstance(token_id, str) or not TOKEN_ID_RE.match(token_id):
        raise ExportError("令牌 ID 格式无效")
    verification = verify_bundle(bundle_dir)
    if not verification["ok"]:
        raise ExportError("投影包校验失败:\n" + "\n".join("- " + item for item in verification["errors"]))
    manifest = verification["manifest"]
    digest = verification["digest"]
    required = required_class(manifest)
    directory = authorizations_dir(project)
    path = directory / (token_id + ".json")
    if not path.is_file():
        raise ExportError("令牌不存在: %s" % token_id)
    with file_lock(directory / ".lock"):
        try:
            with path.open("r", encoding="utf-8") as stream:
                record = json.load(stream)
        except (OSError, ValueError) as exc:
            raise ExportError("无法读取令牌: %s" % exc)
        if not isinstance(record, dict):
            raise ExportError("令牌记录无效")
        if record.get("schema_version") != SCHEMA_VERSION:
            raise ExportError("令牌 schema_version 无效")
        if record.get("token_id") != token_id:
            raise ExportError("令牌 ID 不匹配")
        if record.get("used_at"):
            raise ExportError("令牌已使用")
        if parse_time(record.get("expires_at", "")) <= _now():
            raise ExportError("令牌已过期")
        if record.get("bundle_digest") != digest:
            raise ExportError("令牌与投影包摘要不匹配")
        if record.get("recipient") != recipient_name:
            raise ExportError("令牌接收方不匹配")
        from .a2a_policy import class_index

        if class_index(record.get("max_class")) < class_index(required):
            raise ExportError("令牌分类上限不足")
        record["used_at"] = iso(_now())
        nuclearlib.atomic_write_json(path, record)
    return record
