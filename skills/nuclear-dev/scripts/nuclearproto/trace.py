#!/usr/bin/env python3
"""门禁运行轨迹（trace）：一次判定看到了什么，事后还能复核。

轨迹是线索，不是证据，也不参与门禁判定：门禁通不通过只由 ``nuclearlib`` 决定。
轨迹回答的是另一个问题——"当时那把门禁看到的是哪些产物、哪些原话、哪个版本"。

标准见 ``skills/nuclear-dev/references/tracing.md``；本模块只实现它。三条硬保证：

1. **关掉就是空操作**：未启用时 ``Tracer`` 不建目录、不写文件，调用方照常运行；
2. **错误不越界**：写轨迹的任何失败都只报告，不改变判定结论，也不改变退出码；
3. **导入即安全**：导入本模块不需要任何配置，也不产生副作用。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import nuclearlib

from .audit import RULES_SHA256, RULES_VERSION, _FileLock

TRACE_SCHEMA_VERSION = 1
TRACES_DIR = "traces"
LOCK_FILE = ".lock"
GENESIS = "0" * 64
TRACE_ID_PREFIX = "TRC-"
ENV_ENABLED = "NUCLEAR_DEV_TRACE"
ENV_ACTOR = "NUCLEAR_DEV_TRACE_ACTOR"
TRUTHY = {"1", "true", "yes", "on"}

#: 轨迹里的时间戳都走同一个函数：与内核记的 `captured_at` 同一种格式、同一个时钟。
NOW = nuclearlib.utc_now


class TraceError(Exception):
    """轨迹读写失败；调用方必须把它当成"没写成"，而不是判定失败。"""


# --- 基础工具 -------------------------------------------------------


def traces_root(root: Path) -> Path:
    return nuclearlib.state_path(root) / TRACES_DIR


def enabled(flag: bool = False) -> bool:
    """是否写轨迹：命令行开关优先，其次环境变量，都没有就不写。"""
    if flag:
        return True
    return str(os.environ.get(ENV_ENABLED, "")).strip().lower() in TRUTHY


def actor() -> str:
    return str(os.environ.get(ENV_ACTOR, "")).strip() or "nuclearctl"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return nuclearlib.canonical_json(value)


def _millis() -> int:
    return int(round(time.monotonic() * 1000))


def record_digest(record: Dict[str, Any]) -> str:
    """记录自身的摘要：去掉 ``record_sha256`` 后按规范 JSON 求 SHA-256。"""
    payload = {key: value for key, value in record.items() if key != "record_sha256"}
    return _sha256_text(_canonical(payload))


def environment() -> Dict[str, Any]:
    """轨迹里记下的运行环境：换台机器重跑时，这决定了两次判定可比不可比。"""
    return {
        "kit_version": RULES_VERSION,
        "schema_version": nuclearlib.SCHEMA_VERSION,
        "rules_sha256": RULES_SHA256,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
    }


def file_digest(path: Path) -> Optional[str]:
    try:
        return nuclearlib.sha256_file(path)
    except OSError:
        return None


def artifact_digests(root: Path, stages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """产物与批准文件此刻的摘要；缺席的记为 ``present: false``，不是错误。

    ``stages`` 给定时只取这些阶段——门禁看过的那些，而不是整个工作区：
    记多了会把与这次判定无关的改动也算成偏离。
    """
    digests: List[Dict[str, Any]] = []
    for stage in stages or nuclearlib.STAGES:
        relative = nuclearlib.STAGE_ARTIFACTS[stage]
        path = nuclearlib.stage_path(root, stage)
        digests.append(
            {
                "stage": stage,
                "path": relative,
                "present": path.is_file(),
                "sha256": file_digest(path) if path.is_file() else None,
            }
        )
    approval = nuclearlib.state_path(root) / "approvals"
    for stage in stages or nuclearlib.STAGES:
        path = approval / (stage + ".json")
        if path.is_file():
            digests.append(
                {
                    "stage": stage,
                    "path": "approvals/" + stage + ".json",
                    "present": True,
                    "sha256": file_digest(path),
                }
            )
    return digests


# --- span 与一次运行 ------------------------------------------------


class Span:
    """一个 span：名字、类别、属性、事件与耗时。"""

    def __init__(self, data: Dict[str, Any], run: "Tracer") -> None:
        self.data = data
        self._run = run

    @property
    def span_id(self) -> str:
        return str(self.data["span_id"])

    def set(self, attributes: Optional[Dict[str, Any]] = None) -> None:
        if attributes:
            self.data["attributes"].update(attributes)

    def event(self, name: str) -> None:
        self.data["events"].append({"time": NOW(), "name": name})

    def error(self, message: str) -> None:
        self.data["status"] = "error"
        self.data["attributes"].setdefault("error", message)

    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc is not None:
            self.error("%s: %s" % (exc_type.__name__, exc))
        self._run._close(self.data)


class Tracer:
    """一次运行的轨迹收集器；未启用时所有方法都是空操作。"""

    def __init__(
        self,
        root: Path,
        kind: str,
        *,
        stage: Optional[str] = None,
        trace_id: Optional[str] = None,
        started_at: Optional[str] = None,
        on: bool = True,
    ) -> None:
        self.root = Path(root)
        self.kind = kind
        self.stage = stage
        self.on = on
        self.started_at = started_at or NOW()
        self.trace_id = trace_id or self._new_id()
        self.spans: List[Dict[str, Any]] = []
        self._open: List[Dict[str, Any]] = []
        self._started = _millis()
        self._counters: Dict[str, int] = {}

    # 身份：TRC-<UTC 时间>-<6 位随机>；只用文件名安全字符，Windows 也能落盘。
    def _new_id(self) -> str:
        stamp = self.started_at.replace("-", "").replace(":", "")
        if stamp.endswith("Z"):
            stamp = stamp[:-1] + "Z"
        return "%s%s-%s" % (TRACE_ID_PREFIX, stamp, os.urandom(3).hex())

    def _next_span_id(self, parent: Optional[str]) -> str:
        if parent is None:
            number = self._counters.get("", 0) + 1
            self._counters[""] = number
            return "S%d" % number
        number = self._counters.get(parent, 0) + 1
        self._counters[parent] = number
        return "%s.%d" % (parent, number)

    def span(self, name: str, kind: str = "check", attributes: Optional[Dict[str, Any]] = None) -> Span:
        if not self.on:
            return _NOOP_SPAN
        parent = self._open[-1] if self._open else None
        data = {
            "span_id": self._next_span_id(parent["span_id"] if parent else None),
            "parent_span_id": parent["span_id"] if parent else None,
            "name": name,
            "kind": kind,
            "start": NOW(),
            "end": None,
            "duration_ms": None,
            "status": "ok",
            "attributes": dict(attributes or {}),
            "events": [],
        }
        self.spans.append(data)
        self._open.append(data)
        data["_started"] = _millis()
        return Span(data, self)

    def _close(self, data: Dict[str, Any]) -> None:
        started = data.pop("_started", None)
        data["end"] = NOW()
        data["duration_ms"] = None if started is None else _millis() - started
        if self._open and self._open[-1] is data:
            self._open.pop()

    def record(self, verdict: Dict[str, Any], artifacts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """收尾并落盘；未启用时返回 ``None``。任何写失败都抛 ``TraceError``。"""
        if not self.on:
            return None
        for data in list(self._open):
            self._close(data)
        payload: Dict[str, Any] = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "kind": self.kind,
            "stage": self.stage,
            "root": str(self.root),
            "actor": actor(),
            "started_at": self.started_at,
            "finished_at": NOW(),
            "duration_ms": _millis() - self._started,
            "environment": environment(),
            "spans": self.spans,
            "verdict": verdict,
        }
        if artifacts is not None:
            payload["artifacts"] = artifacts
        _write(self.root, payload)
        return payload


class _NoopSpan(Span):
    """未启用时的 span：什么都记，也什么都不写。"""

    def __init__(self) -> None:
        super().__init__({}, None)  # type: ignore[arg-type]

    def set(self, attributes: Optional[Dict[str, Any]] = None) -> None:
        return None

    def event(self, name: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


_NOOP_SPAN = _NoopSpan()


def record_gate(
    root: Path,
    stage: str,
    *,
    include_dependencies: bool,
    errors: List[str],
    on: bool = True,
) -> Optional[Dict[str, Any]]:
    """把一次 ``gate`` 判定记成轨迹：根 span 是这次门禁，子 span 是逐个阶段的自检。

    阶段自检返回的错误是判定内容，不是轨迹故障：span 的 ``status`` 仍为 ``ok``，
    错误写在 ``attributes.errors`` 里，逐字保留内核原话。
    """
    tracer = Tracer(root, "gate", stage=stage, on=on)
    names = nuclearlib.STAGES[: nuclearlib.STAGES.index(stage) + 1] if include_dependencies else [stage]
    with tracer.span(
        "gate." + stage,
        kind="gate",
        attributes={
            "stage": stage,
            "include_dependencies": include_dependencies,
            "ok": not errors,
            "error_count": len(errors),
            "errors": list(errors),
            "stage_artifacts": [nuclearlib.STAGE_ARTIFACTS[name] for name in names],
        },
    ) as span:
        span.event("gate.evaluated")
        for name in names:
            with tracer.span("stage.check." + name, kind="check", attributes={"stage": name}) as child:
                own = nuclearlib.stage_gate(root, name, include_dependencies=False)
                child.set({"ok": not own, "error_count": len(own), "errors": own})
                child.event("stage.checked")
        span.event("artifacts.hashed")
    return tracer.record({"ok": not errors, "errors": list(errors)}, artifact_digests(root, names))


# --- 落盘、串联与阅读 ----------------------------------------------


def _record_files(root: Path) -> List[Path]:
    directory = traces_root(root)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(TRACE_ID_PREFIX + "*.json") if path.is_file())


def _read(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError:
        raise TraceError("轨迹不存在: %s" % path.name)
    except OSError as exc:
        raise TraceError("轨迹无法读取: %s: %s" % (path.name, exc))
    except ValueError as exc:
        raise TraceError("轨迹不是有效 JSON: %s: %s" % (path.name, exc))
    if not isinstance(value, dict):
        raise TraceError("轨迹格式无效: %s" % path.name)
    return value


def _ordered(root: Path) -> List[Dict[str, Any]]:
    records = [_read(path) for path in _record_files(root)]
    records.sort(key=lambda record: (int(record.get("sequence", 0)), str(record.get("trace_id", ""))))
    return records


def _write(root: Path, record: Dict[str, Any]) -> Path:
    """在锁内接上序号与前序摘要并落盘：两条轨迹不会抢到同一个位置。"""
    directory = traces_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(record["trace_id"]) + ".json")
    temporary = path.with_name(path.name + ".tmp")
    try:
        with _FileLock(directory / LOCK_FILE):
            ordered = _ordered(root)
            if ordered:
                last = ordered[-1]
                record["sequence"] = int(last.get("sequence", 0)) + 1
                record["prev_record_sha256"] = str(last.get("record_sha256") or GENESIS)
            else:
                record["sequence"] = 1
                record["prev_record_sha256"] = GENESIS
            record["record_sha256"] = record_digest(record)
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(path))
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise TraceError("轨迹写入失败: %s: %s" % (path, exc))
    return path


def summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """列表里一行：够人认出来，不用读整个轨迹。"""
    verdict = record.get("verdict") or {}
    errors = verdict.get("errors") or []
    return {
        "trace_id": record.get("trace_id"),
        "sequence": record.get("sequence"),
        "kind": record.get("kind"),
        "stage": record.get("stage"),
        "actor": record.get("actor"),
        "started_at": record.get("started_at"),
        "duration_ms": record.get("duration_ms"),
        "ok": bool(verdict.get("ok")),
        "error_count": len(errors),
        "spans": len(record.get("spans") or []),
        "record_sha256": record.get("record_sha256"),
    }


def list_traces(root: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """按序号倒序列出轨迹摘要；未初始化的工作区返回空列表。"""
    records = _ordered(root)
    records.reverse()
    if limit is not None and limit >= 0:
        records = records[:limit]
    return [summary(record) for record in records]


def load_trace(root: Path, trace_id: str) -> Dict[str, Any]:
    """按标识读一条轨迹；标识会被限定在轨迹目录内，不接受路径。"""
    if not trace_id or "/" in trace_id or "\\" in trace_id or trace_id.startswith("."):
        raise TraceError("轨迹标识无效: %s" % trace_id)
    directory = traces_root(root)
    path = (directory / (trace_id + ".json")).resolve()
    if not nuclearlib.is_within(directory.resolve(), path):
        raise TraceError("轨迹标识越出轨迹目录: %s" % trace_id)
    if not path.is_file():
        raise TraceError("轨迹不存在: %s" % trace_id)
    return _read(path)


def verify(root: Path) -> Dict[str, Any]:
    """校验轨迹链：序号连续、摘要自洽、前序链接正确。

    另外报告 ``drift``——某阶段产物或批准文件在轨迹写下之后变了。产物变化本身是正常的
    工程活动，不等于篡改，所以它单独列出，不影响 ``ok``；它说明的是"这条轨迹描述的
    已经不是现在这份产物"，需要重新跑一次门禁。
    """
    errors: List[str] = []
    drift: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    try:
        records = _ordered(root)
    except TraceError as exc:
        return {"ok": False, "traces": 0, "head": GENESIS, "errors": [str(exc)], "drift": []}
    previous = GENESIS
    for index, record in enumerate(records, 1):
        trace_id = str(record.get("trace_id") or "?")
        if int(record.get("schema_version", 0)) != TRACE_SCHEMA_VERSION:
            errors.append("%s: 轨迹 schema_version 不是 %d" % (trace_id, TRACE_SCHEMA_VERSION))
        if int(record.get("sequence", 0)) != index:
            errors.append("%s: 序号为 %s，应为 %d" % (trace_id, record.get("sequence"), index))
        if str(record.get("prev_record_sha256") or "") != previous:
            errors.append("%s: 前序链接与上一条轨迹的摘要不一致" % trace_id)
        if record_digest(record) != str(record.get("record_sha256") or ""):
            errors.append("%s: 记录摘要自校验失败" % trace_id)
        previous = str(record.get("record_sha256") or GENESIS)
        for item in record.get("artifacts") or []:
            if not item.get("present"):
                continue
            path = nuclearlib.state_path(root) / str(item.get("path") or "")
            current = file_digest(path) if path.is_file() else None
            if current is None:
                drift.append({"trace_id": trace_id, "path": item.get("path"), "state": "removed"})
            elif current != item.get("sha256"):
                drift.append({"trace_id": trace_id, "path": item.get("path"), "state": "changed"})
    return {
        "ok": not errors,
        "traces": len(records),
        "head": previous,
        "errors": errors,
        "drift": drift,
    }
