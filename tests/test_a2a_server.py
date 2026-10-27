#!/usr/bin/env python3
"""A2A 服务端：认证、入站校验、任务状态与配置边界。"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import support

from nuclearproto import a2a_client, a2a_policy, a2a_projection, a2a_server, auth
from nuclearproto.a2a_tasks import TaskStore
from test_a2a_cli import write_policy
from test_a2a_client import CARD_ORG, SPEC, write_key_file


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._server_temp = tempfile.TemporaryDirectory()
        self._dev_temp = tempfile.TemporaryDirectory()
        self._exchange_temp = tempfile.TemporaryDirectory()
        self.server_root = Path(self._server_temp.name)
        self.dev_root = Path(self._dev_temp.name)
        self.exchange = Path(self._exchange_temp.name)

        support.build_valid_project(self.dev_root)
        write_policy(self.dev_root)
        policy = a2a_policy.ExportPolicy.load(self.dev_root)
        self.bundle = a2a_projection.build_bundle(self.dev_root, "vv-org", policy)

        self.server_keys = Path(self._server_temp.name) / "server-keys.json"
        write_key_file(self.server_keys, "vv-org", "dev-org")
        self.server_store = auth.KeyStore(self.server_keys)
        self.server_store.load()
        self.client_keys = Path(self._server_temp.name) / "client-keys.json"
        write_key_file(self.client_keys, "dev-org", "vv-org")
        self.client_store = auth.KeyStore(self.client_keys)
        self.client_store.load()

        self.server = self.make_server()
        self.peer = {
            "agent_id": "vv-org",
            "organization": CARD_ORG,
            "endpoint": "http://127.0.0.1:%d/a2a" % self.server.port,
            "transfer_root": str(self.exchange),
        }
        self.config = {
            "agent": {"agent_id": "dev-org", "organization": "开发组织", "spec_revision": SPEC},
            "peers": {"vv-org": self.peer},
        }
        self.card = a2a_client.fetch_card(self.peer, self.config)
        self.staged = a2a_client.stage_bundle(self.dev_root, self.peer, self.bundle["bundle_dir"])

    def tearDown(self) -> None:
        self.server.shutdown()
        self._server_temp.cleanup()
        self._dev_temp.cleanup()
        self._exchange_temp.cleanup()

    def make_server(self, **overrides) -> a2a_server.A2AServer:
        config = a2a_server.ServerConfig(
            project=self.server_root,
            agent_id="vv-org",
            organization=CARD_ORG,
            spec_revision=SPEC,
            store=self.server_store,
            bind=overrides.get("bind", "127.0.0.1"),
            port=0,
            tls_cert=overrides.get("tls_cert"),
            tls_key=overrides.get("tls_key"),
            trust_proxy_tls=overrides.get("trust_proxy_tls", False),
            transfer_root=str(self.exchange),
            rate_per_minute=overrides.get("rate_per_minute", 1000),
            rate_burst=overrides.get("rate_burst", 1000),
            max_body=overrides.get("max_body", a2a_server.MAX_BODY_BYTES),
        )
        server = a2a_server.create_server(config)
        server.start()
        return server

    def signed_post(self, payload, store=None, extra_headers=None, port=None, content_type="application/json"):
        store = store or self.client_store
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        key = store.signing_key("vv-org")
        headers = auth.sign_request(key["secret"], key["keyid"], "POST", "/a2a", body)
        headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            "http://127.0.0.1:%d/a2a" % (port or self.server.port),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            exc.close()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except Exception:
                parsed = {"raw": raw.decode("utf-8", "replace")}
            return exc.code, parsed

    def message(self, parts, metadata=None, request_id="r-1"):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/send",
            "params": {
                "message": {"role": "user", "parts": parts},
                "metadata": metadata
                or {"protocol_profile": a2a_client.PROTOCOL_PROFILE, "spec_revision": SPEC},
            },
        }

    # --- 正常流程 -------------------------------------------------

    def test_agent_card(self) -> None:
        self.assertEqual(self.card["card"]["agent_id"], "vv-org")
        self.assertFalse(self.card["card"]["capabilities"]["streaming"])

    def test_send_task_and_query(self) -> None:
        result = a2a_client.send_task(
            self.peer, self.client_store, self.card, self.bundle["bundle_dir"], self.staged["transfer_ref"]
        )
        task_id = result["task"]["id"]
        store = TaskStore(self.server_root)
        record = store.get(task_id)
        self.assertEqual(record["peer"], "dev-org")
        self.assertEqual(record["state"], "submitted")
        self.assertTrue(all(item["verified"] for item in record["files"]))
        self.assertTrue(
            (self.server_root / ".nuclear-dev" / "a2a" / "inbox" / task_id / "request.json").is_file()
        )
        status = a2a_client.get_task(self.peer, self.client_store, task_id)
        self.assertEqual(status["status"]["state"], "submitted")

    def test_cancel_task(self) -> None:
        result = a2a_client.send_task(
            self.peer, self.client_store, self.card, self.bundle["bundle_dir"], self.staged["transfer_ref"]
        )
        task_id = result["task"]["id"]
        canceled = a2a_client.cancel_task(self.peer, self.client_store, task_id)
        self.assertEqual(canceled["status"]["state"], "canceled")
        again = a2a_client.cancel_task(self.peer, self.client_store, task_id)
        self.assertEqual(again["status"]["state"], "canceled")

    # --- 拒绝路径 -------------------------------------------------

    def test_wrong_secret_is_rejected(self) -> None:
        bad_keys = Path(self._server_temp.name) / "bad-keys.json"
        write_key_file(bad_keys, "dev-org", "vv-org", secret=b"X" * 32)
        bad_store = auth.KeyStore(bad_keys)
        bad_store.load()
        status, _ = self.signed_post(self.message([{"kind": "text", "text": "hi"}]), store=bad_store)
        self.assertEqual(status, 401)

    def test_inline_file_bytes_are_rejected(self) -> None:
        payload = self.message(
            [
                {
                    "kind": "file",
                    "file": {
                        "name": "x",
                        "transferId": "b/x",
                        "size": 4,
                        "sha256": "0" * 64,
                        "bytes": "AAAA",
                    },
                }
            ]
        )
        status, body = self.signed_post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], a2a_server.RPC_INVALID_PARAMS)

    def test_unknown_method_is_rejected(self) -> None:
        payload = {"jsonrpc": "2.0", "id": "r", "method": "tasks/explode", "params": {}}
        status, body = self.signed_post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], a2a_server.RPC_METHOD_NOT_FOUND)

    def test_missing_task_is_not_found(self) -> None:
        payload = {"jsonrpc": "2.0", "id": "r", "method": "tasks/get", "params": {"id": "T-000000000000"}}
        status, body = self.signed_post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], a2a_server.RPC_TASK_NOT_FOUND)

    def test_file_digest_mismatch_is_rejected(self) -> None:
        target = self.exchange / "forged" / "file.txt"
        target.parent.mkdir(parents=True)
        target.write_text("actual content\n", encoding="utf-8")
        payload = self.message(
            [
                {
                    "kind": "file",
                    "file": {
                        "name": "file.txt",
                        "transferId": "forged/file.txt",
                        "size": target.stat().st_size,
                        "sha256": "0" * 64,
                    },
                }
            ]
        )
        status, body = self.signed_post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], a2a_server.RPC_INVALID_PARAMS)

    def test_missing_file_leaves_task_input_required(self) -> None:
        payload = self.message(
            [
                {
                    "kind": "file",
                    "file": {
                        "name": "missing.txt",
                        "transferId": "missing/missing.txt",
                        "size": 3,
                        "sha256": "0" * 64,
                    },
                }
            ]
        )
        status, body = self.signed_post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["status"]["state"], "input-required")
        task = TaskStore(self.server_root).get(body["result"]["id"])
        self.assertFalse(task["files"][0]["verified"])

    def test_content_type_is_required(self) -> None:
        payload = self.message([{"kind": "text", "text": "hi"}])
        status, _ = self.signed_post(payload, content_type="text/plain")
        self.assertEqual(status, 415)

    def test_oversized_body_is_rejected(self) -> None:
        server = self.make_server(max_body=512)
        try:
            status, _ = self.signed_post(b"x" * 1024, port=server.port)
            self.assertEqual(status, 413)
        finally:
            server.shutdown()

    def test_rate_limit(self) -> None:
        server = self.make_server(rate_per_minute=1, rate_burst=1)
        try:
            first, _ = self.signed_post(
                {"jsonrpc": "2.0", "id": "1", "method": "tasks/get", "params": {"id": "T-000000000000"}},
                port=server.port,
            )
            second, _ = self.signed_post(
                {"jsonrpc": "2.0", "id": "2", "method": "tasks/get", "params": {"id": "T-000000000000"}},
                port=server.port,
            )
            self.assertEqual(first, 200)
            self.assertEqual(second, 429)
        finally:
            server.shutdown()

    # --- 配置边界 -------------------------------------------------

    def test_non_loopback_requires_tls(self) -> None:
        config = a2a_server.ServerConfig(
            project=self.server_root,
            agent_id="vv-org",
            organization=CARD_ORG,
            spec_revision=SPEC,
            store=self.server_store,
            bind="0.0.0.0",
            transfer_root=str(self.exchange),
        )
        with self.assertRaises(a2a_server.ServerError):
            a2a_server.create_server(config)

    def test_proxy_mode_requires_loopback(self) -> None:
        config = a2a_server.ServerConfig(
            project=self.server_root,
            agent_id="vv-org",
            organization=CARD_ORG,
            spec_revision=SPEC,
            store=self.server_store,
            bind="0.0.0.0",
            trust_proxy_tls=True,
            transfer_root=str(self.exchange),
        )
        with self.assertRaises(a2a_server.ServerError):
            a2a_server.create_server(config)

    def test_proxy_mode_requires_forwarded_https(self) -> None:
        server = self.make_server(trust_proxy_tls=True)
        try:
            payload = {"jsonrpc": "2.0", "id": "1", "method": "tasks/get", "params": {"id": "T-000000000000"}}
            status, _ = self.signed_post(payload, port=server.port)
            self.assertEqual(status, 400)
            status, _ = self.signed_post(
                payload, port=server.port, extra_headers={"X-Forwarded-Proto": "https"}
            )
            self.assertEqual(status, 200)
        finally:
            server.shutdown()

    def test_unpinned_spec_revision_is_rejected(self) -> None:
        config = a2a_server.ServerConfig(
            project=self.server_root,
            agent_id="vv-org",
            organization=CARD_ORG,
            spec_revision="unpinned",
            store=self.server_store,
            transfer_root=str(self.exchange),
        )
        with self.assertRaises(a2a_server.ServerError):
            a2a_server.create_server(config)


if __name__ == "__main__":
    unittest.main()
