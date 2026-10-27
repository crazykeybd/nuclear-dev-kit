#!/usr/bin/env python3
"""服务端任务账本的回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support

from nuclearproto.a2a_tasks import TaskError, TaskStore, public_task


class TaskStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.store = TaskStore(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def create(self, files=None):
        return self.store.create("dev-org", {"message": {"role": "user", "parts": []}}, files or [])

    def test_create_persists_and_writes_inbox(self) -> None:
        task = self.create()
        self.assertRegex(task["id"], r"^T-[0-9a-f]{12}$")
        self.assertEqual(task["state"], "submitted")
        self.assertTrue((self.root / ".nuclear-dev" / "a2a" / "inbox" / task["id"] / "request.json").is_file())
        reopened = TaskStore(self.root)
        self.assertEqual(reopened.get(task["id"])["id"], task["id"])

    def test_unverified_files_require_input(self) -> None:
        task = self.create(files=[{"name": "requirements.json", "transfer_id": "b/requirements.json", "size": 1, "sha256": "0" * 64, "verified": False}])
        self.assertEqual(task["state"], "input-required")
        self.assertTrue(task["notes"])

    def test_ownership_is_enforced(self) -> None:
        task = self.create()
        self.assertEqual(self.store.get_for_peer(task["id"], "dev-org")["id"], task["id"])
        with self.assertRaises(TaskError):
            self.store.get_for_peer(task["id"], "other-org")

    def test_state_transitions(self) -> None:
        task = self.create()
        working = self.store.transition(task["id"], "working", "开始审查")
        self.assertEqual(working["state"], "working")
        completed = self.store.transition(task["id"], "completed", "报告完成")
        self.assertEqual(completed["state"], "completed")
        with self.assertRaises(TaskError):
            self.store.transition(task["id"], "working")
        self.assertEqual(self.store.transition(task["id"], "completed")["state"], "completed")

    def test_cancel_is_terminal_and_idempotent(self) -> None:
        task = self.create()
        canceled = self.store.transition(task["id"], "canceled", "对端取消")
        self.assertEqual(canceled["state"], "canceled")
        self.assertEqual(self.store.transition(task["id"], "canceled")["state"], "canceled")
        with self.assertRaises(TaskError):
            self.store.transition(task["id"], "working")

    def test_artifacts(self) -> None:
        task = self.create()
        updated = self.store.add_artifact(
            task["id"],
            {"name": "vv-report.json", "file": "vv-report.json", "transferId": task["id"] + "/vv-report.json", "size": 10, "sha256": "1" * 64, "class": "C2"},
        )
        self.assertEqual(len(updated["artifacts"]), 1)
        self.assertEqual(public_task(updated)["artifacts"][0]["name"], "vv-report.json")

    def test_invalid_ids_are_rejected(self) -> None:
        with self.assertRaises(TaskError):
            self.store.get("bogus")
        with self.assertRaises(TaskError):
            self.store.transition("T-zzz", "working")


if __name__ == "__main__":
    unittest.main()
