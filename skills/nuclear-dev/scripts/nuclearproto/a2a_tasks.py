#!/usr/bin/env python3
"""A2A 服务端任务账本：状态机、持久化与跨进程锁。"""

from __future__ import annotations

import copy
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import nuclearlib

from .audit import file_lock

SCHEMA_VERSION = 1
TASK_ID_RE = re.compile(r"^T-[0-9a-f]{12}$")
STATES = ["submitted", "working", "input-required", "completed", "failed", "canceled"]
TERMINAL_STATES = {"completed", "failed", "canceled"}
TRANSITIONS = {
    "submitted": {"working", "input-required", "failed", "canceled"},
    "working": {"input-required", "completed", "failed", "canceled"},
    "input-required": {"working", "completed", "failed", "canceled"},
    "completed": set(),
    "failed": set(),
    "canceled": set(),
}
MAX_TASKS = 10000


class TaskError(Exception):
    """任务不存在、状态转移非法或存储失败。"""


def _now() -> str:
    return nuclearlib.utc_now()


class TaskStore:
    def __init__(self, project: Path) -> None:
        self.project = Path(project)
        self.directory = self.project / ".nuclear-dev" / "a2a"
        self.path = self.directory / "tasks.json"
        self.lock_path = self.directory / ".tasks.lock"

    def _load(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": SCHEMA_VERSION, "tasks": []}
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError) as exc:
            raise TaskError("无法读取任务账本: %s" % exc)
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            raise TaskError("任务账本 schema_version 无效")
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise TaskError("任务账本 tasks 必须是数组")
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        nuclearlib.atomic_write_json(self.path, data)

    def list(self) -> List[Dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._load().get("tasks", [])]

    def get(self, task_id: str) -> Dict[str, Any]:
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            raise TaskError("任务 ID 格式无效")
        for item in self._load().get("tasks", []):
            if item.get("id") == task_id:
                return copy.deepcopy(item)
        raise TaskError("任务不存在: %s" % task_id)

    def get_for_peer(self, task_id: str, peer: str) -> Dict[str, Any]:
        task = self.get(task_id)
        if task.get("peer") != peer:
            raise TaskError("任务不存在: %s" % task_id)
        return task

    def create(self, peer: str, request: Dict[str, Any], files: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(peer, str) or not peer.strip():
            raise TaskError("peer 不能为空")
        with file_lock(self.lock_path):
            data = self._load()
            tasks = data.setdefault("tasks", [])
            if len(tasks) >= MAX_TASKS:
                raise TaskError("任务数量达到上限")
            task_id = self._new_id(tasks)
            now = _now()
            state = "submitted"
            notes: List[str] = []
            unverified = [item for item in files if not item.get("verified")]
            if unverified:
                state = "input-required"
                notes.append("有 %d 个文件尚未通过带外校验" % len(unverified))
            record = {
                "schema_version": SCHEMA_VERSION,
                "id": task_id,
                "peer": peer,
                "state": state,
                "created_at": now,
                "updated_at": now,
                "request": request,
                "files": files,
                "artifacts": [],
                "notes": notes,
                "history": [{"at": now, "state": state, "note": "任务已接收"}],
            }
            inbox = self.directory / "inbox" / task_id
            inbox.mkdir(parents=True, exist_ok=True)
            nuclearlib.atomic_write_json(
                inbox / "request.json",
                {
                    "schema_version": SCHEMA_VERSION,
                    "peer": peer,
                    "received_at": now,
                    "request": request,
                    "files": files,
                },
            )
            tasks.append(record)
            self._save(data)
        return copy.deepcopy(record)

    def _new_id(self, tasks: List[Dict[str, Any]]) -> str:
        used = {item.get("id") for item in tasks}
        for _ in range(20):
            candidate = "T-" + secrets.token_hex(6)
            if candidate not in used:
                return candidate
        raise TaskError("无法生成唯一任务 ID")

    def transition(self, task_id: str, state: str, note: Optional[str] = None) -> Dict[str, Any]:
        if state not in STATES:
            raise TaskError("未知任务状态: %s" % state)
        with file_lock(self.lock_path):
            data = self._load()
            task = self._find(data, task_id)
            current = task.get("state")
            if current == state:
                return copy.deepcopy(task)
            if state not in TRANSITIONS.get(current, set()):
                raise TaskError("非法状态转移: %s -> %s" % (current, state))
            now = _now()
            task["state"] = state
            task["updated_at"] = now
            if note:
                task.setdefault("notes", []).append(note)
            task.setdefault("history", []).append({"at": now, "state": state, "note": note or ""})
            self._save(data)
            return copy.deepcopy(task)

    def add_artifact(self, task_id: str, artifact: Dict[str, Any]) -> Dict[str, Any]:
        with file_lock(self.lock_path):
            data = self._load()
            task = self._find(data, task_id)
            if task.get("state") in ("canceled", "failed"):
                raise TaskError("已终止的任务不能添加产物")
            task.setdefault("artifacts", []).append(artifact)
            task["updated_at"] = _now()
            self._save(data)
            return copy.deepcopy(task)

    @staticmethod
    def _find(data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            raise TaskError("任务 ID 格式无效")
        for item in data.get("tasks", []):
            if item.get("id") == task_id:
                return item
        raise TaskError("任务不存在: %s" % task_id)


def public_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """返回给对端的视图：不包含内部备注与历史。"""
    return {
        "id": task.get("id"),
        "status": {
            "state": task.get("state"),
            "timestamp": task.get("updated_at"),
        },
        "artifacts": task.get("artifacts", []),
    }
