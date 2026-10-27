#!/usr/bin/env python3
"""带哈希链、跨进程锁与外部 sink 的审计日志。

审计是线索，不是证据：它不参与门禁判定，也不能替代阶段产物。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import nuclearlib

RULES_VERSION = nuclearlib.KIT_VERSION
SCHEMA_VERSION = nuclearlib.SCHEMA_VERSION
GENESIS = "0" * 64
STATE_FILE = "state.json"
LOCK_FILE = ".lock"
STATE_SCHEMA_VERSION = 1


class AuditError(Exception):
    """审计写入、sink 投递或校验失败。"""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


RULES_SHA256 = _sha256_file(Path(nuclearlib.__file__).resolve())


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class _FileLock:
    """跨进程独占锁；POSIX 用 flock，Windows 用 msvcrt.locking。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        if os.fstat(self.fd).st_size == 0:
            os.write(self.fd, b"\0")
        os.lseek(self.fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_EX)
        except OSError as exc:
            os.close(self.fd)
            self.fd = None
            raise AuditError("无法获取审计锁: %s" % exc)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is None:
            return
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None


def file_lock(path: Path) -> _FileLock:
    """供同包其他模块复用同一套跨进程锁。"""
    return _FileLock(Path(path))


def _read_state(state_dir: Path) -> Optional[Dict[str, Any]]:
    path = state_dir / STATE_FILE
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(state_dir: Path, state: Dict[str, Any]) -> None:
    path = state_dir / STATE_FILE
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def _audit_files(state_dir: Path) -> List[Path]:
    if not state_dir.is_dir():
        return []
    return sorted(state_dir.glob("*.jsonl"))


def _last_record(state_dir: Path) -> Optional[Dict[str, Any]]:
    for path in reversed(_audit_files(state_dir)):
        try:
            with path.open("r", encoding="utf-8") as stream:
                lines = [line for line in stream if line.strip()]
        except OSError:
            continue
        if not lines:
            continue
        try:
            value = json.loads(lines[-1])
        except ValueError:
            return None
        return value if isinstance(value, dict) else None
    return None


def current_head(state_dir: Path) -> Dict[str, Any]:
    """返回当前链头；不修改任何文件。"""
    state_dir = Path(state_dir)
    state = _read_state(state_dir)
    record = _last_record(state_dir)
    if state and isinstance(state.get("seq"), int) and isinstance(state.get("head"), str):
        return {
            "ok": True,
            "seq": state["seq"],
            "head": state["head"],
            "file": state.get("file"),
            "state_consistent": record is None
            or (record.get("seq") == state["seq"] and record.get("sha256") == state["head"]),
        }
    if record is None:
        return {"ok": True, "seq": 0, "head": GENESIS, "file": None, "state_consistent": True}
    return {
        "ok": True,
        "seq": record.get("seq"),
        "head": record.get("sha256"),
        "file": None,
        "timestamp": record.get("timestamp"),
        "state_consistent": True,
    }


def statement_hint(head: Dict[str, Any]) -> str:
    return "audit_head=%s seq=%s" % (head.get("head"), head.get("seq"))


def _deliver(sink: Dict[str, Any], line: str) -> None:
    kind = sink.get("type")
    if kind == "file":
        path = Path(sink["path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise AuditError("审计 sink 文件写入失败: %s" % exc)
        return
    if kind == "https":
        headers = {"Content-Type": "application/x-ndjson"}
        token = sink.get("token")
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            sink["url"], data=(line + "\n").encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if getattr(response, "status", 200) >= 300:
                    raise AuditError("审计 sink 返回状态 %s" % response.status)
        except AuditError:
            raise
        except Exception as exc:
            raise AuditError("审计 sink 推送失败: %s" % exc)
        return
    raise AuditError("未知审计 sink 类型: %s" % kind)


class AuditLog:
    """单个项目 `.nuclear-dev/audit/` 的追加器。"""

    def __init__(
        self,
        state_dir: Path,
        actor: str = "unknown",
        sinks: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.actor = actor or "unknown"
        self.sinks = list(sinks or [])

    def append(
        self,
        tool: str,
        workspace: str,
        project_path: str,
        arguments: Dict[str, Any],
        phase: str,
        ok: Optional[bool] = None,
        is_error: bool = False,
        exit_code: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with _FileLock(self.state_dir / LOCK_FILE):
            state = _read_state(self.state_dir)
            if state and isinstance(state.get("seq"), int) and isinstance(state.get("head"), str):
                seq, prev = state["seq"], state["head"]
            else:
                record = _last_record(self.state_dir)
                if record is None:
                    seq, prev = 0, GENESIS
                else:
                    seq, prev = int(record.get("seq", 0)), str(record.get("sha256") or GENESIS)
            record = {
                "schema_version": STATE_SCHEMA_VERSION,
                "seq": seq + 1,
                "timestamp": nuclearlib.utc_now(),
                "tool": tool,
                "phase": phase,
                "actor": self.actor,
                "workspace": workspace,
                "project_path": project_path,
                "arguments_sha256": _sha256_text(canonical(arguments)),
                "ok": ok,
                "is_error": bool(is_error),
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "rules_version": RULES_VERSION,
                "kit_sha256": RULES_SHA256,
                "prev_sha256": prev,
            }
            record["sha256"] = _sha256_text(canonical(record))
            line = json.dumps(record, ensure_ascii=False, sort_keys=True)
            date = str(record["timestamp"])[:10]
            path = self.state_dir / (date + ".jsonl")
            try:
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                raise AuditError("审计写入失败: %s" % exc)
            _write_state(
                self.state_dir,
                {
                    "schema_version": STATE_SCHEMA_VERSION,
                    "seq": record["seq"],
                    "head": record["sha256"],
                    "file": path.name,
                },
            )
            for sink in self.sinks:
                _deliver(sink, line)
        return record


def verify(state_dir: Path) -> Dict[str, Any]:
    """校验哈希链、序号连续性与状态文件一致性。"""
    state_dir = Path(state_dir)
    errors: List[str] = []
    files = _audit_files(state_dir)
    expected_seq = 1
    previous = GENESIS
    count = 0
    last: Optional[Dict[str, Any]] = None
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as stream:
                lines = stream.read().splitlines()
        except OSError as exc:
            errors.append("无法读取 %s: %s" % (path.name, exc))
            continue
        for index, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                errors.append("%s:%d: 不是有效 JSON" % (path.name, index))
                continue
            if not isinstance(record, dict):
                errors.append("%s:%d: 记录不是对象" % (path.name, index))
                continue
            count += 1
            stored = record.get("sha256")
            body = dict(record)
            body.pop("sha256", None)
            actual = _sha256_text(canonical(body))
            if stored != actual:
                errors.append("%s:%d: 记录哈希不匹配（seq=%s）" % (path.name, index, record.get("seq")))
            if record.get("seq") != expected_seq:
                errors.append(
                    "%s:%d: 序号不连续，期望 %d，实际 %s" % (path.name, index, expected_seq, record.get("seq"))
                )
            if record.get("prev_sha256") != previous:
                errors.append("%s:%d: 链断裂（seq=%s）" % (path.name, index, record.get("seq")))
            expected_seq = (record.get("seq") or expected_seq) + 1
            previous = str(stored or actual)
            last = record
    state = _read_state(state_dir)
    if state and isinstance(state.get("seq"), int) and isinstance(state.get("head"), str):
        if last is None:
            errors.append("状态文件存在但日志为空（可能被截断）")
        elif state["seq"] != last.get("seq") or state["head"] != last.get("sha256"):
            errors.append("状态文件与日志尾部不一致（可能被截断或替换）")
    return {
        "ok": not errors,
        "records": count,
        "errors": errors,
        "head": last.get("sha256") if last else GENESIS,
        "seq": last.get("seq") if last else 0,
    }


def build_sinks(values: List[str], token_file: Optional[str], workspace_roots: List[Path]) -> List[Dict[str, Any]]:
    """把命令行值转换为 sink 配置，并拒绝把 file sink 放进 workspace。"""
    token: Optional[str] = None
    if token_file:
        try:
            token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise AuditError("无法读取审计 sink 令牌文件: %s" % exc)
        if not token:
            raise AuditError("审计 sink 令牌文件为空")
    sinks: List[Dict[str, Any]] = []
    roots = [Path(root).resolve() for root in workspace_roots]
    for value in values:
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme in ("http", "https"):
            if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "::1", "localhost"):
                raise AuditError("审计 HTTPS sink 只允许 https，或 loopback 上的 http: %s" % value)
            sink: Dict[str, Any] = {"type": "https", "url": value}
            if token:
                sink["token"] = token
            sinks.append(sink)
            continue
        path = Path(value).expanduser().resolve()
        for root in roots:
            try:
                path.relative_to(root)
            except ValueError:
                continue
            raise AuditError("审计 sink 文件不得位于 workspace 内: %s" % path)
        sinks.append({"type": "file", "path": str(path)})
    return sinks


def warn(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
