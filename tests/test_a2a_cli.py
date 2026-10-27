#!/usr/bin/env python3
"""A2A CLI：投影计划、非交互拒绝与策略前置条件的回归测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

from nuclearproto import a2a_client, a2a_export, a2a_policy, a2a_projection, auth
from nuclearproto.a2a_tasks import TaskStore
from test_a2a_client import CARD_ORG, FakeA2A, SPEC, write_key_file


def write_policy(project: Path, allow_c3: bool = True) -> None:
    payload = {
        "schema_version": 1,
        "default": "deny",
        "recipients": {
            "vv-org": {
                "organization": "示例 V&V 组织",
                "max_class": "C3",
                "projections": ["requirements", "test_summary", "vv_scope"],
                "allow_c3_raw": allow_c3,
            },
            "read-only-org": {
                "organization": "只读组织",
                "max_class": "C2",
                "projections": ["requirements"],
                "allow_c3_raw": False,
            },
        },
    }
    path = project / ".nuclear-dev" / "a2a" / "export-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    classification = {
        "schema_version": 1,
        "entries": [{"path": "src/solver.py", "class": "C3", "transferable": True}],
    }
    (path.parent / "classification.json").write_text(json.dumps(classification), encoding="utf-8")


class A2ACliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        support.build_valid_project(self.root)
        write_policy(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_cli(self, *argv):
        completed = support.run_script(
            support.A2A, ["--project", str(self.root), "--json"] + [str(item) for item in argv]
        )
        payload = support.parse_json(completed.stdout) if completed.stdout.strip() else {}
        return completed, payload

    def test_policy_template(self) -> None:
        completed, payload = self.run_cli("policy-template")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["template"]["default"], "deny")
        self.assertIn("classification_template", payload)

    def test_plan_creates_verifiable_bundle(self) -> None:
        completed, payload = self.run_cli("plan", "--recipient", "vv-org")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["ok"], payload)
        verification = a2a_projection.verify_bundle(Path(payload["bundle_dir"]))
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertEqual(verification["digest"], payload["digest"])
        self.assertIn("requirements", payload["projections"])

    def test_plan_without_policy_is_denied(self) -> None:
        (self.root / ".nuclear-dev" / "a2a" / "export-policy.json").unlink()
        completed, payload = self.run_cli("plan", "--recipient", "vv-org")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("导出策略", payload["error"])

    def test_raw_without_approval_is_denied(self) -> None:
        completed, payload = self.run_cli(
            "plan", "--recipient", "vv-org", "--raw", "src/solver.py"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("双人特批", payload["error"])

    def test_raw_for_recipient_without_c3_is_denied(self) -> None:
        completed, payload = self.run_cli(
            "plan", "--recipient", "read-only-org", "--raw", "src/solver.py"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("未启用 C3", payload["error"])

    def test_output_outside_project_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            completed, payload = self.run_cli(
                "plan", "--recipient", "vv-org", "--out", str(Path(other) / "outbox")
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("项目目录内", payload["error"])

    def test_authorize_requires_a_tty(self) -> None:
        _, planned = self.run_cli("plan", "--recipient", "vv-org")
        completed, payload = self.run_cli(
            "authorize", "--bundle", planned["bundle_dir"], "--approver", "项目负责人"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("交互终端", payload["error"])

    def test_authorize_rejects_invalid_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            completed, payload = self.run_cli(
                "authorize", "--bundle", other, "--approver", "项目负责人"
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("校验失败", payload["error"])


class SendFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        support.build_valid_project(self.root)
        write_policy(self.root)
        self._other = tempfile.TemporaryDirectory()
        self.exchange = Path(self._other.name) / "exchange"

        server_keys = Path(self._other.name) / "server-keys.json"
        write_key_file(server_keys, "vv-org", "dev-org")
        server_store = auth.KeyStore(server_keys)
        server_store.load()
        self.server = FakeA2A(server_store)

        self.client_keys = Path(self._other.name) / "client-keys.json"
        write_key_file(self.client_keys, "dev-org", "vv-org")
        self.config = Path(self._other.name) / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "agent": {
                        "agent_id": "dev-org",
                        "organization": "开发组织",
                        "spec_revision": SPEC,
                    },
                    "peers": {
                        "vv-org": {
                            "agent_id": "vv-org",
                            "organization": CARD_ORG,
                            "endpoint": "http://127.0.0.1:%d/a2a" % self.server.port,
                            "transfer_root": str(self.exchange),
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.policy = a2a_policy.ExportPolicy.load(self.root)
        self.bundle = a2a_projection.build_bundle(self.root, "vv-org", self.policy)
        peer = a2a_client.get_peer(a2a_client.load_config(self.config), "vv-org")
        self.staged = a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])
        self.token = a2a_export.create_authorization(
            self.root, self.bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )

    def tearDown(self) -> None:
        self.server.close()
        self._temp.cleanup()
        self._other.cleanup()

    def run_send(self):
        return support.run_script(
            support.A2A,
            [
                "--project",
                str(self.root),
                "--json",
                "send",
                "--config",
                str(self.config),
                "--keys",
                str(self.client_keys),
                "--recipient",
                "vv-org",
                "--bundle",
                str(self.bundle["bundle_dir"]),
                "--token",
                self.token["token_id"],
                "--transfer-ref",
                self.staged["transfer_ref"],
            ],
        )

    def audit_records(self):
        files = sorted((self.root / ".nuclear-dev" / "audit").glob("*.jsonl"))
        records = []
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        return records

    def test_send_with_token_succeeds_and_audits(self) -> None:
        completed = self.run_send()
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = support.parse_json(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["task"]["id"], "T-001")
        records = self.audit_records()
        self.assertEqual([item["tool"] for item in records], ["a2a_send", "a2a_send"])
        self.assertEqual([item["phase"] for item in records], ["intent", "result"])
        self.assertTrue(records[-1]["ok"])

    def test_reusing_token_is_rejected(self) -> None:
        first = self.run_send()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_send()
        self.assertEqual(second.returncode, 2)
        payload = support.parse_json(second.stdout)
        self.assertIn("已使用", payload["error"])


class TaskCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self._exchange = tempfile.TemporaryDirectory()
        self.exchange = Path(self._exchange.name)
        self.store = TaskStore(self.root)
        self.task = self.store.create("dev-org", {"message": {"role": "user", "parts": []}}, [])

    def tearDown(self) -> None:
        self._temp.cleanup()
        self._exchange.cleanup()

    def run_cli(self, *argv):
        completed = support.run_script(
            support.A2A, ["--project", str(self.root), "--json"] + [str(item) for item in argv]
        )
        payload = support.parse_json(completed.stdout) if completed.stdout.strip() else {}
        return completed, payload

    def test_list_and_show(self) -> None:
        completed, payload = self.run_cli("task", "list")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["count"], 1)
        completed, payload = self.run_cli("task", "show", "--id", self.task["id"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["task"]["id"], self.task["id"])

    def test_update_state(self) -> None:
        completed, payload = self.run_cli(
            "task", "update", "--id", self.task["id"], "--state", "working", "--note", "开始审查"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["task"]["state"], "working")

    def test_invalid_transition_is_rejected(self) -> None:
        self.store.transition(self.task["id"], "working")
        self.store.transition(self.task["id"], "completed")
        completed, payload = self.run_cli(
            "task", "update", "--id", self.task["id"], "--state", "working"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("非法状态转移", payload["error"])

    def test_artifact_is_copied_and_recorded(self) -> None:
        report = support.write_text(self.root / "vv-report.json", '{"ok": true}\n')
        completed, payload = self.run_cli(
            "task",
            "artifact",
            "--id",
            self.task["id"],
            "--path",
            str(report),
            "--transfer-root",
            str(self.exchange),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        artifact = payload["artifact"]
        self.assertEqual(artifact["transferId"], "%s/vv-report.json" % self.task["id"])
        self.assertTrue((self.exchange / self.task["id"] / "vv-report.json").is_file())
        self.assertEqual(len(TaskStore(self.root).get(self.task["id"])["artifacts"]), 1)

    def test_serve_rejects_non_loopback_without_tls(self) -> None:
        keys = Path(self._exchange.name) / "keys.json"
        write_key_file(keys, "vv-org", "dev-org")
        completed, payload = self.run_cli(
            "serve",
            "--organization",
            CARD_ORG,
            "--spec-revision",
            SPEC,
            "--keys",
            str(keys),
            "--bind",
            "0.0.0.0",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--tls-cert", payload["error"])


if __name__ == "__main__":
    unittest.main()
