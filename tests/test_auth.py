#!/usr/bin/env python3
"""HMAC 请求签名与密钥文件的回归测试。"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import support

from nuclearproto import auth

SECRET_A = b"A" * 32
SECRET_B = b"B" * 32


def encode(secret: bytes) -> str:
    return base64.b64encode(secret).decode("ascii")


def write_keys(path: Path, keys, allowed=("vv-org",), agent="dev-org") -> None:
    payload = {
        "schema_version": 1,
        "agent_id": agent,
        "allowed_peers": list(allowed),
        "keys": keys,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if os.name != "nt":
        os.chmod(str(path), 0o600)


def key_entry(keyid="key-a", secret=SECRET_A, status="current", peer="vv-org", not_after=None):
    entry = {
        "keyid": keyid,
        "peer": peer,
        "status": status,
        "secret": encode(secret),
    }
    if not_after is not None:
        entry["not_after"] = not_after
    return entry


class SignatureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.keys = self.root / "keys.json"
        write_keys(self.keys, [key_entry()])
        self.store = auth.KeyStore(self.keys)
        self.store.load()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_roundtrip(self) -> None:
        body = b'{"jsonrpc":"2.0"}'
        headers = auth.sign_request(SECRET_A, "key-a", "POST", "/a2a", body)
        self.assertTrue(headers["Content-Digest"].startswith("sha-256=:"))
        result = auth.verify_request(headers, "POST", "/a2a", body, self.store, auth.NonceCache())
        self.assertEqual(result["keyid"], "key-a")
        self.assertEqual(result["peer"], "vv-org")

    def test_tampered_body_is_rejected(self) -> None:
        body = b'{"jsonrpc":"2.0"}'
        headers = auth.sign_request(SECRET_A, "key-a", "POST", "/a2a", body)
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "POST", "/a2a", body + b" ", self.store, auth.NonceCache())

    def test_tampered_path_is_rejected(self) -> None:
        body = b"{}"
        headers = auth.sign_request(SECRET_A, "key-a", "POST", "/a2a", body)
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "POST", "/other", body, self.store, auth.NonceCache())

    def test_tampered_method_is_rejected(self) -> None:
        body = b"{}"
        headers = auth.sign_request(SECRET_A, "key-a", "POST", "/a2a", body)
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "PUT", "/a2a", body, self.store, auth.NonceCache())

    def test_expired_timestamp_is_rejected(self) -> None:
        body = b"{}"
        headers = auth.sign_request(
            SECRET_A, "key-a", "POST", "/a2a", body, created=int(time.time()) - 1000
        )
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "POST", "/a2a", body, self.store, auth.NonceCache())

    def test_nonce_replay_is_rejected(self) -> None:
        body = b"{}"
        headers = auth.sign_request(SECRET_A, "key-a", "POST", "/a2a", body)
        nonces = auth.NonceCache()
        auth.verify_request(headers, "POST", "/a2a", body, self.store, nonces)
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "POST", "/a2a", body, self.store, nonces)

    def test_unknown_keyid_is_rejected(self) -> None:
        body = b"{}"
        headers = auth.sign_request(SECRET_A, "missing-key", "POST", "/a2a", body)
        with self.assertRaises(auth.AuthError):
            auth.verify_request(headers, "POST", "/a2a", body, self.store, auth.NonceCache())

    def test_missing_headers_are_rejected(self) -> None:
        with self.assertRaises(auth.AuthError):
            auth.verify_request({}, "POST", "/a2a", b"{}", self.store, auth.NonceCache())

    def test_signature_input_parser(self) -> None:
        params_text, params = auth.parse_signature_input(
            'sig1=("@method" "@path" "content-digest");created=1;nonce="abc";keyid="key-a";alg="hmac-sha256"'
        )
        self.assertIn('created=1', params_text)
        self.assertEqual(params["nonce"], "abc")
        self.assertEqual(params["keyid"], "key-a")
        self.assertEqual(params["alg"], "hmac-sha256")


class KeyStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.keys = self.root / "keys.json"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def assert_invalid(self, keys, allowed=("vv-org",)) -> None:
        write_keys(self.keys, keys, allowed=allowed)
        with self.assertRaises(auth.AuthError):
            auth.KeyStore(self.keys).load()

    def test_short_secret_is_rejected(self) -> None:
        self.assert_invalid([key_entry(secret=b"short")])

    def test_duplicate_keyid_is_rejected(self) -> None:
        self.assert_invalid(
            [key_entry(keyid="dup"), key_entry(keyid="dup", status="next", secret=SECRET_B)]
        )

    def test_peer_not_allowed_is_rejected(self) -> None:
        self.assert_invalid([key_entry(peer="other-org")])

    def test_invalid_status_is_rejected(self) -> None:
        self.assert_invalid([key_entry(status="active")])

    def test_peer_without_keys_is_rejected(self) -> None:
        self.assert_invalid([key_entry()], allowed=("vv-org", "another-org"))

    def test_expired_key_is_not_usable_for_signing(self) -> None:
        write_keys(self.keys, [key_entry(not_after="2000-01-01T00:00:00Z")])
        store = auth.KeyStore(self.keys)
        store.load()
        with self.assertRaises(auth.AuthError):
            store.signing_key("vv-org")

    def test_rotation_accepts_current_next_and_retiring(self) -> None:
        write_keys(
            self.keys,
            [
                key_entry(keyid="old", secret=SECRET_A, status="retiring"),
                key_entry(keyid="new", secret=SECRET_B, status="current"),
            ],
        )
        store = auth.KeyStore(self.keys)
        store.load()
        body = b"{}"
        for keyid, secret in (("old", SECRET_A), ("new", SECRET_B)):
            headers = auth.sign_request(secret, keyid, "POST", "/a2a", body)
            result = auth.verify_request(headers, "POST", "/a2a", body, store, auth.NonceCache())
            self.assertEqual(result["keyid"], keyid)
        self.assertEqual(store.signing_key("vv-org")["keyid"], "new")

    def test_reload_on_mtime_change(self) -> None:
        write_keys(self.keys, [key_entry(keyid="old")])
        store = auth.KeyStore(self.keys)
        store.load()
        time.sleep(0.01)
        write_keys(self.keys, [key_entry(keyid="new", secret=SECRET_B)])
        self.assertEqual(store.signing_key("vv-org")["keyid"], "new")

    @unittest.skipIf(os.name == "nt", "Windows 无法用标准库检查 ACL")
    def test_wide_permissions_are_rejected(self) -> None:
        write_keys(self.keys, [key_entry()])
        os.chmod(str(self.keys), 0o644)
        with self.assertRaises(auth.AuthError):
            auth.KeyStore(self.keys).load()


if __name__ == "__main__":
    unittest.main()
