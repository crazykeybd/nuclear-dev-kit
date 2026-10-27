#!/usr/bin/env python3
"""MCP 写入面与审计日志测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

READ_ONLY_TOOLS = [
    "nuclear_status",
    "nuclear_gate",
    "nuclear_validate",
    "nuclear_read_artifact",
    "nuclear_schema",
    "nuclear_evidence_list",
]
WRITE_TOOLS = ["nuclear_init", "nuclear_evidence_add", "nuclear_manifest"]


class WriteToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def client(self, allow_write: bool) -> support.McpClient:
        return support.McpClient([self.root], allow_write=allow_write)

    def test_write_tools_hidden_without_flag(self) -> None:
        with self.client(False) as client:
            client.initialize()
            response = client.request("tools/list")
        names = [item["name"] for item in response["result"]["tools"]]
        self.assertEqual(names, READ_ONLY_TOOLS)

    def test_write_tools_exposed_with_flag(self) -> None:
        with self.client(True) as client:
            client.initialize()
            response = client.request("tools/list")
        names = [item["name"] for item in response["result"]["tools"]]
        self.assertEqual(names, READ_ONLY_TOOLS + WRITE_TOOLS)
        for name in names:
            self.assertNotIn("approve", name.lower())
            self.assertNotIn("sign", name.lower())

    def test_instructions_describe_write_scope(self) -> None:
        with self.client(True) as client:
            result = client.initialize()["result"]
        self.assertIn("nuclear_evidence_add", result["instructions"])
        self.assertIn("不会生成批准", result["instructions"])

    def test_evidence_add_registers_new_file(self) -> None:
        new_file = support.write_text(self.root / "evidence" / "extra.log", "extra evidence\n")
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_evidence_add",
                {
                    "path": "evidence/extra.log",
                    "kind": "test-log",
                    "producer": "示例测试夹具",
                    "command": "fixture",
                    "result": "passed",
                },
            )
        self.assertFalse(is_error)
        self.assertEqual(payload["evidence"]["id"], "EVID-015")
        self.assertEqual(payload["evidence"]["sha256"], support.sha256_file(new_file))

    def test_evidence_add_rejects_duplicate_path(self) -> None:
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_evidence_add",
                {
                    "path": "evidence/build.log",
                    "kind": "build-log",
                    "producer": "示例测试夹具",
                    "command": "fixture",
                    "result": "passed",
                },
            )
        self.assertTrue(is_error)
        self.assertIn("已登记证据", payload["error"])

    def test_evidence_add_rejects_absolute_path(self) -> None:
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_evidence_add",
                {
                    "path": str(self.root / "evidence" / "build.log"),
                    "kind": "build-log",
                    "producer": "示例测试夹具",
                    "command": "fixture",
                    "result": "passed",
                },
            )
        self.assertTrue(is_error)
        self.assertIn("绝对路径", payload["error"])

    def test_evidence_add_rejects_path_outside_project(self) -> None:
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_evidence_add",
                {
                    "path": "../../outside.log",
                    "kind": "build-log",
                    "producer": "示例测试夹具",
                    "command": "fixture",
                    "result": "passed",
                },
            )
        self.assertTrue(is_error)
        self.assertIn("越出项目目录", payload["error"])

    def test_manifest_is_generated_and_version_checked(self) -> None:
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_manifest", {"version": "1.0.0"})
            self.assertFalse(is_error, payload)
            self.assertTrue(Path(payload["path"]).is_file())
            second, second_error = client.payload("nuclear_manifest", {"version": "2.0.0"})
        self.assertTrue(second_error)
        self.assertIn("版本不匹配", second["error"])

    def test_manifest_requires_release_gate(self) -> None:
        (self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"]).unlink()
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_manifest", {"version": "1.0.0"})
        self.assertTrue(is_error)
        self.assertIn("发布门禁未通过", payload["error"])


class InitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_init_creates_workspace_and_audit(self) -> None:
        with support.McpClient([self.root], allow_write=True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_init", {"name": "示例核能软件", "id": "example-nuclear"}
            )
        self.assertFalse(is_error, payload)
        self.assertEqual(payload["project"]["project_id"], "example-nuclear")
        self.assertTrue((self.root / ".nuclear-dev" / "project.json").is_file())
        records = _audit_records(self.root)
        self.assertEqual(records[-1]["tool"], "nuclear_init")

    def test_init_twice_is_reported_as_error(self) -> None:
        with support.McpClient([self.root], allow_write=True) as client:
            client.initialize()
            client.payload("nuclear_init", {"id": "example-nuclear"})
            payload, is_error = client.payload("nuclear_init", {"id": "example-nuclear"})
        self.assertTrue(is_error)
        self.assertIn("已初始化", payload["error"])


class AuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_audit_records_every_tool_call_when_write_enabled(self) -> None:
        with support.McpClient([self.root], allow_write=True) as client:
            client.initialize()
            client.payload("nuclear_status")
            client.payload("nuclear_gate", {"stage": "release"})
        records = _audit_records(self.root)
        self.assertEqual([item["tool"] for item in records], ["nuclear_status", "nuclear_gate"])
        for record in records:
            self.assertEqual(len(record["arguments_sha256"]), 64)
            self.assertIn("rules_version", record)
            self.assertEqual(len(record["kit_sha256"]), 64)
            self.assertIn("duration_ms", record)
            self.assertNotIn("approval", json.dumps(record).lower())

    def test_audit_is_not_written_in_read_only_mode(self) -> None:
        with support.McpClient([self.root], allow_write=False) as client:
            client.initialize()
            client.payload("nuclear_gate", {"stage": "release"})
        self.assertFalse((self.root / ".nuclear-dev" / "audit").exists())

    def test_audit_records_failed_tool_calls(self) -> None:
        with support.McpClient([self.root], allow_write=True) as client:
            client.initialize()
            client.payload("nuclear_evidence_add", {"path": "../x", "kind": "k", "producer": "p", "command": "c", "result": "passed"})
        records = _audit_records(self.root)
        self.assertTrue(records[-1]["is_error"])
        self.assertEqual(records[-1]["tool"], "nuclear_evidence_add")

    def test_gate_does_not_change_artifacts_even_with_write_enabled(self) -> None:
        before = _artifact_snapshot(self.root)
        with support.McpClient([self.root], allow_write=True) as client:
            client.initialize()
            client.payload("nuclear_gate", {"stage": "release"})
        self.assertEqual(before, _artifact_snapshot(self.root))

    def test_audit_sink_inside_workspace_refuses_start(self) -> None:
        completed = support.run_script(
            support.MCP,
            [
                "--workspace",
                str(self.root),
                "--allow-write",
                "--audit-sink",
                str(self.root / "audit.jsonl"),
            ],
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("不得位于 workspace", completed.stderr)

    def test_state_changing_call_fails_closed_when_sink_is_down(self) -> None:
        manifest = self.root / ".nuclear-dev" / "manifests" / "software-configuration-manifest-1.0.0.json"
        with support.McpClient(
            [self.root],
            allow_write=True,
            extra_args=["--audit-sink", "http://127.0.0.1:1/audit"],
        ) as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_manifest", {"version": "1.0.0"})
        self.assertTrue(is_error)
        self.assertIn("审计写入失败", payload["error"])
        self.assertFalse(manifest.exists())
        records = _audit_records(self.root)
        self.assertEqual(records[-1]["tool"], "nuclear_manifest")
        self.assertEqual(records[-1]["phase"], "intent")

    def test_read_only_call_survives_sink_failure(self) -> None:
        with support.McpClient(
            [self.root],
            allow_write=True,
            extra_args=["--audit-sink", "http://127.0.0.1:1/audit"],
        ) as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_status")
        self.assertFalse(is_error)
        self.assertTrue(payload["ok"])
        self.assertTrue(all(record["passed"] for record in payload["stages"].values()))


def _audit_records(root: Path):
    files = sorted((root / ".nuclear-dev" / "audit").glob("*.jsonl"))
    if not files:
        return []
    records = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _artifact_snapshot(root: Path):
    state = root / ".nuclear-dev"
    return {
        path.relative_to(root).as_posix(): support.sha256_file(path)
        for path in sorted(state.rglob("*"))
        if path.is_file() and "audit" not in path.relative_to(state).parts
    }


if __name__ == "__main__":
    unittest.main()
