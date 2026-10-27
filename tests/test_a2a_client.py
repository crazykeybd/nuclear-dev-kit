#!/usr/bin/env python3
"""A2A 客户端：agent card 校验、带外暂存、签名请求与任务查询。"""

from __future__ import annotations

import base64
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

import support

from nuclearproto import a2a_client, a2a_export, a2a_policy, a2a_projection, auth

SPEC = "sha256:test-spec-revision"
SECRET = b"S" * 32
CARD_ORG = "示例 V&V 组织"


def write_key_file(path: Path, agent_id: str, peer: str, keyid: str = "key-1", secret: bytes = SECRET):
    payload = {
        "schema_version": 1,
        "agent_id": agent_id,
        "allowed_peers": [peer],
        "keys": [
            {
                "keyid": keyid,
                "peer": peer,
                "status": "current",
                "secret": base64.b64encode(secret).decode("ascii"),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    if os.name != "nt":
        # KeyStore 在 POSIX 上要求密钥文件 0600；默认 umask 会写成 0644
        os.chmod(str(path), 0o600)


def write_policy(project: Path) -> None:
    payload = {
        "schema_version": 1,
        "default": "deny",
        "recipients": {
            "vv-org": {
                "organization": CARD_ORG,
                "max_class": "C3",
                "projections": ["requirements", "design_summary", "test_summary", "vv_scope"],
                "allow_c3_raw": True,
            }
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


class FakeA2A:
    def __init__(self, key_store: auth.KeyStore, spec_revision: str = SPEC) -> None:
        self.store = key_store
        self.nonces = auth.NonceCache()
        self.requests = []
        self.tasks = {}
        self.spec_revision = spec_revision
        self.card = {
            "schema_version": 1,
            "agent_id": "vv-org",
            "organization": CARD_ORG,
            "protocol_profile": a2a_client.PROTOCOL_PROFILE,
            "spec_revision": spec_revision,
            "capabilities": {"streaming": False, "pushNotifications": False},
            "security": {"scheme": "hmac-sha256"},
        }
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def _handler(self):
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                return

            def _send(self, status: int, payload) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path == "/.well-known/agent-card.json":
                    self._send(200, outer.card)
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                headers = {key: value for key, value in self.headers.items()}
                try:
                    auth.verify_request(headers, "POST", self.path, body, outer.store, outer.nonces)
                except auth.AuthError:
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                message = json.loads(body.decode("utf-8"))
                outer.requests.append({"path": self.path, "message": message})
                method = message.get("method")
                if method == "message/send":
                    task_id = "T-%03d" % (len(outer.tasks) + 1)
                    outer.tasks[task_id] = {"id": task_id, "status": {"state": "working"}}
                    result = {"id": task_id, "status": {"state": "submitted"}}
                elif method == "tasks/get":
                    task_id = message.get("params", {}).get("id")
                    outer.tasks[task_id] = {"id": task_id, "status": {"state": "completed"}}
                    result = outer.tasks[task_id]
                elif method == "tasks/cancel":
                    task_id = message.get("params", {}).get("id")
                    outer.tasks[task_id] = {"id": task_id, "status": {"state": "canceled"}}
                    result = outer.tasks[task_id]
                else:
                    self._send(200, {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32601, "message": "unknown"}})
                    return
                self._send(200, {"jsonrpc": "2.0", "id": message.get("id"), "result": result})

        return Handler

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class ClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self._other = tempfile.TemporaryDirectory()
        self.exchange = Path(self._other.name) / "exchange"
        support.build_valid_project(self.root)
        write_policy(self.root)
        self.policy = a2a_policy.ExportPolicy.load(self.root)
        self.bundle = a2a_projection.build_bundle(self.root, "vv-org", self.policy)

        self.server_keys = Path(self._other.name) / "server-keys.json"
        write_key_file(self.server_keys, "vv-org", "dev-org")
        self.server_store = auth.KeyStore(self.server_keys)
        self.server_store.load()
        self.server = FakeA2A(self.server_store)

        self.client_keys = Path(self._other.name) / "client-keys.json"
        write_key_file(self.client_keys, "dev-org", "vv-org")
        self.client_store = auth.KeyStore(self.client_keys)
        self.client_store.load()

        self.config_path = Path(self._other.name) / "a2a-config.json"
        self.config = {
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
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def tearDown(self) -> None:
        self.server.close()
        self._temp.cleanup()
        self._other.cleanup()

    def test_card_and_send_flow(self) -> None:
        peer = a2a_client.get_peer(self.config, "vv-org")
        card = a2a_client.fetch_card(peer, self.config)
        self.assertEqual(card["card"]["agent_id"], "vv-org")
        staged = a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])
        result = a2a_client.send_task(
            peer, self.client_store, card, self.bundle["bundle_dir"], staged["transfer_ref"]
        )
        self.assertEqual(result["task"]["id"], "T-001")
        sent = self.server.requests[-1]["message"]
        self.assertEqual(sent["method"], "message/send")
        parts = sent["params"]["message"]["parts"]
        files = [part for part in parts if part["kind"] == "file"]
        self.assertTrue(files)
        for part in files:
            self.assertNotIn("bytes", part["file"])
            self.assertIn("transferId", part["file"])
        self.assertEqual(sent["params"]["metadata"]["transfer_ref"], staged["transfer_ref"])

    def test_wrong_secret_is_rejected(self) -> None:
        write_key_file(self.client_keys, "dev-org", "vv-org", secret=b"X" * 32)
        store = auth.KeyStore(self.client_keys)
        store.load()
        peer = a2a_client.get_peer(self.config, "vv-org")
        card = a2a_client.fetch_card(peer, self.config)
        staged = a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])
        with self.assertRaises(a2a_client.ClientError) as caught:
            a2a_client.send_task(peer, store, card, self.bundle["bundle_dir"], staged["transfer_ref"])
        self.assertIn("401", str(caught.exception))

    def test_spec_revision_mismatch_is_rejected(self) -> None:
        self.server.card["spec_revision"] = "sha256:other"
        peer = a2a_client.get_peer(self.config, "vv-org")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.fetch_card(peer, self.config)

    def test_streaming_capability_is_rejected(self) -> None:
        self.server.card["capabilities"]["streaming"] = True
        peer = a2a_client.get_peer(self.config, "vv-org")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.fetch_card(peer, self.config)

    def test_stage_requires_external_transfer_root(self) -> None:
        peer = dict(a2a_client.get_peer(self.config, "vv-org"))
        peer["transfer_root"] = str(self.root / "exchange")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])

    def test_send_requires_staged_bundle(self) -> None:
        peer = a2a_client.get_peer(self.config, "vv-org")
        card = a2a_client.fetch_card(peer, self.config)
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.send_task(peer, self.client_store, card, self.bundle["bundle_dir"], "missing")

    def test_tampered_staged_bundle_is_rejected(self) -> None:
        peer = a2a_client.get_peer(self.config, "vv-org")
        card = a2a_client.fetch_card(peer, self.config)
        staged = a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])
        target = Path(staged["path"]) / "requirements.json"
        target.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.send_task(peer, self.client_store, card, self.bundle["bundle_dir"], staged["transfer_ref"])

    def test_status_and_cancel(self) -> None:
        peer = a2a_client.get_peer(self.config, "vv-org")
        card = a2a_client.fetch_card(peer, self.config)
        staged = a2a_client.stage_bundle(self.root, peer, self.bundle["bundle_dir"])
        sent = a2a_client.send_task(
            peer, self.client_store, card, self.bundle["bundle_dir"], staged["transfer_ref"]
        )
        task_id = sent["task"]["id"]
        status = a2a_client.get_task(peer, self.client_store, task_id)
        self.assertEqual(status["status"]["state"], "completed")
        canceled = a2a_client.cancel_task(peer, self.client_store, task_id)
        self.assertEqual(canceled["status"]["state"], "canceled")

    def test_config_rejects_remote_plain_http(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["peers"]["vv-org"]["endpoint"] = "http://example.com/a2a"
        path = Path(self._other.name) / "bad-config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.load_config(path)

    def test_config_rejects_unpinned_spec_revision(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["agent"]["spec_revision"] = "unpinned"
        path = Path(self._other.name) / "bad-config-2.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(a2a_client.ClientError):
            a2a_client.load_config(path)

    def test_config_rejects_same_organization(self) -> None:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data["peers"]["vv-org"]["organization"] = data["agent"]["organization"]
        path = Path(self._other.name) / "bad-config-3.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(a2a_client.ClientError) as caught:
            a2a_client.load_config(path)
        self.assertIn("独立 V&V", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
