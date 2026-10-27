#!/usr/bin/env python3
"""CLI 基础行为回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support


class CliBasicsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_init_creates_workspace_layout(self) -> None:
        code, payload, err = support.ctl(
            self.root, "init", "--name", "示例核能软件", "--id", "example-nuclear", "--json"
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["project"]["project_id"], "example-nuclear")
        state = self.root / ".nuclear-dev"
        for relative in ["project.json", "traceability.json", "evidence/index.json"]:
            self.assertTrue((state / relative).is_file(), relative)
        for stage in support.STAGES:
            self.assertTrue((state / "stages" / stage).is_dir(), stage)
        self.assertTrue((state / "approvals").is_dir())
        self.assertTrue((state / "manifests").is_dir())

    def test_init_twice_is_rejected(self) -> None:
        code, _, err = support.ctl(self.root, "init", "--json")
        self.assertEqual(code, 0, err)
        code, _, err = support.ctl(self.root, "init", "--json")
        self.assertEqual(code, 2)
        self.assertIn("已初始化", err)

    def test_status_before_init_is_all_blocked_and_exits_zero(self) -> None:
        code, payload, err = support.ctl(self.root, "status", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(payload["stages"]), sorted(support.STAGES))
        for stage, record in payload["stages"].items():
            self.assertFalse(record["passed"], stage)
            self.assertTrue(record["errors"], stage)

    def test_gate_before_init_reports_missing_workspace(self) -> None:
        code, payload, _ = support.ctl(self.root, "gate", "plan", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("未初始化" in item for item in payload["errors"]))

    def test_gate_rejects_unknown_stage(self) -> None:
        completed = support.run_script(support.CTL, ["--root", str(self.root), "gate", "bogus"])
        self.assertEqual(completed.returncode, 2)

    def test_no_approve_subcommand_exists(self) -> None:
        completed = support.run_script(support.CTL, ["--root", str(self.root), "approve", "plan"])
        self.assertEqual(completed.returncode, 2)

    def test_unknown_command_exits_two(self) -> None:
        completed = support.run_script(support.CTL, ["--root", str(self.root), "publish"])
        self.assertEqual(completed.returncode, 2)

    def test_evidence_add_registers_sequential_ids(self) -> None:
        support.ctl(self.root, "init", "--json")
        first = support.write_text(self.root / "evidence" / "first.log", "first\n")
        second = support.write_text(self.root / "evidence" / "second.log", "second\n")
        for path, expected in [(first, "EVID-001"), (second, "EVID-002")]:
            code, payload, err = support.ctl(
                self.root,
                "evidence",
                "add",
                str(path),
                "--kind",
                "test-log",
                "--producer",
                "测试",
                "--command",
                "fixture",
                "--result",
                "passed",
                "--json",
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(payload["evidence"]["id"], expected)

    def test_evidence_add_rejects_duplicate_path(self) -> None:
        support.ctl(self.root, "init", "--json")
        path = support.write_text(self.root / "evidence" / "dup.log", "dup\n")
        argv = [
            "evidence",
            "add",
            str(path),
            "--kind",
            "test-log",
            "--producer",
            "测试",
            "--command",
            "fixture",
            "--result",
            "passed",
            "--json",
        ]
        self.assertEqual(support.ctl(self.root, *argv)[0], 0)
        code, _, err = support.ctl(self.root, *argv)
        self.assertEqual(code, 2)
        self.assertIn("已登记证据", err)

    def test_evidence_add_rejects_path_outside_project(self) -> None:
        support.ctl(self.root, "init", "--json")
        with tempfile.TemporaryDirectory() as outside_temp:
            outside = support.write_text(Path(outside_temp) / "outside.log", "outside\n")
            code, _, err = support.ctl(
                self.root,
                "evidence",
                "add",
                str(outside),
                "--kind",
                "test-log",
                "--producer",
                "测试",
                "--command",
                "fixture",
                "--result",
                "passed",
                "--json",
            )
        self.assertEqual(code, 2)
        self.assertIn("必须位于项目目录内", err)

    def test_evidence_add_rejects_failed_result_value(self) -> None:
        support.ctl(self.root, "init", "--json")
        path = support.write_text(self.root / "evidence" / "bad.log", "bad\n")
        code, _, err = support.ctl(
            self.root,
            "evidence",
            "add",
            str(path),
            "--kind",
            "test-log",
            "--producer",
            "测试",
            "--command",
            "fixture",
            "--result",
            "unknown",
            "--json",
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
