#!/usr/bin/env python3
"""MCP 的 nuclear_a2a_send：C2 发送、令牌消费与 C3 拒绝。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

from nuclearproto import a2a_client, a2a_export, a2a_policy, a2a_projection, auth
from test_a2a_cli import write_policy
from test_a2a_client import CARD_ORG, FakeA2A, SPEC, write_key_file


class McpA2ASendTest(unittest.TestCase):
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
        self.bundle_rel = self.bundle["bundle_dir"].relative_to(self.root).as_posix()

    def tearDown(self) -> None:
        self.server.close()
        self._temp.cleanup()
        self._other.cleanup()

    def client(self, with_a2a: bool = True) -> support.McpClient:
        extra = []
        if with_a2a:
            extra = ["--a2a-config", str(self.config), "--a2a-keys", str(self.client_keys)]
        return support.McpClient([self.root], allow_write=True, extra_args=extra)

    def test_tool_is_exposed_only_with_a2a_config(self) -> None:
        with self.client(True) as client:
            client.initialize()
            names = [item["name"] for item in client.request("tools/list")["result"]["tools"]]
        self.assertIn("nuclear_a2a_send", names)
        with self.client(False) as client:
            client.initialize()
            names = [item["name"] for item in client.request("tools/list")["result"]["tools"]]
        self.assertNotIn("nuclear_a2a_send", names)

    def test_send_c2_bundle(self) -> None:
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_a2a_send",
                {
                    "recipient": "vv-org",
                    "bundle": self.bundle_rel,
                    "token": self.token["token_id"],
                    "transfer_ref": self.staged["transfer_ref"],
                },
            )
        self.assertFalse(is_error, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["task"]["id"], "T-001")
        records = self.audit_records()
        self.assertEqual([item["tool"] for item in records], ["nuclear_a2a_send", "nuclear_a2a_send"])
        self.assertEqual([item["phase"] for item in records], ["intent", "result"])

    def test_token_cannot_be_reused(self) -> None:
        with self.client(True) as client:
            client.initialize()
            client.payload(
                "nuclear_a2a_send",
                {
                    "recipient": "vv-org",
                    "bundle": self.bundle_rel,
                    "token": self.token["token_id"],
                    "transfer_ref": self.staged["transfer_ref"],
                },
            )
            payload, is_error = client.payload(
                "nuclear_a2a_send",
                {
                    "recipient": "vv-org",
                    "bundle": self.bundle_rel,
                    "token": self.token["token_id"],
                    "transfer_ref": self.staged["transfer_ref"],
                },
            )
        self.assertTrue(is_error)
        self.assertIn("已使用", payload["error"])

    def test_c3_bundle_is_rejected_over_mcp(self) -> None:
        digest = support.sha256_file(self.root / "src" / "solver.py")
        from test_a2a_export import write_exp

        write_exp(self.root, [{"path": "src/solver.py", "sha256": digest, "class": "C3"}])
        approvals = a2a_export.load_export_approvals(self.root, "vv-org", self.policy)
        covered = a2a_export.cover_raw_entries(
            [{"path": "src/solver.py", "sha256": digest}], approvals
        )
        bundle = a2a_projection.build_bundle(
            self.root, "vv-org", self.policy, raw_entries=covered
        )
        peer = a2a_client.get_peer(a2a_client.load_config(self.config), "vv-org")
        a2a_client.stage_bundle(self.root, peer, bundle["bundle_dir"])
        token = a2a_export.create_authorization(
            self.root, bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )
        relative = bundle["bundle_dir"].relative_to(self.root).as_posix()
        with self.client(True) as client:
            client.initialize()
            payload, is_error = client.payload(
                "nuclear_a2a_send",
                {"recipient": "vv-org", "bundle": relative, "token": token["token_id"]},
            )
        self.assertTrue(is_error)
        self.assertIn("只能从 CLI", payload["error"])

    def test_a2a_without_allow_write_refuses_start(self) -> None:
        completed = support.run_script(
            support.MCP,
            [
                "--workspace",
                str(self.root),
                "--a2a-config",
                str(self.config),
                "--a2a-keys",
                str(self.client_keys),
            ],
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--allow-write", completed.stderr)

    def test_bundle_outside_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            with self.client(True) as client:
                client.initialize()
                payload, is_error = client.payload(
                    "nuclear_a2a_send",
                    {
                        "recipient": "vv-org",
                        "bundle": str(Path(other).resolve()),
                        "token": self.token["token_id"],
                    },
                )
        self.assertTrue(is_error)
        self.assertIn("相对路径", payload["error"])

    def audit_records(self):
        files = sorted((self.root / ".nuclear-dev" / "audit").glob("*.jsonl"))
        records = []
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        return records


if __name__ == "__main__":
    unittest.main()
