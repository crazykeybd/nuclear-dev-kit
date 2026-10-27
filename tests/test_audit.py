#!/usr/bin/env python3
"""审计哈希链、锁、sink 与 CLI 的回归测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

from nuclearproto import audit


def make_log(root: Path, sinks=None) -> audit.AuditLog:
    return audit.AuditLog(root / ".nuclear-dev" / "audit", actor="tester", sinks=sinks)


def append(log: audit.AuditLog, index: int = 0, phase: str = "result", **extra):
    payload = {
        "tool": "nuclear_status",
        "workspace": "example",
        "project_path": "/example",
        "arguments": {"index": index},
        "phase": phase,
    }
    payload.update(extra)
    return log.append(**payload)


def read_lines(root: Path):
    files = sorted((root / ".nuclear-dev" / "audit").glob("*.jsonl"))
    lines = []
    for path in files:
        lines.extend(line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return files, lines


class ChainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.state = self.root / ".nuclear-dev" / "audit"
        self.log = make_log(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_first_record_is_genesis(self) -> None:
        record = append(self.log)
        self.assertEqual(record["seq"], 1)
        self.assertEqual(record["prev_sha256"], audit.GENESIS)
        self.assertEqual(len(record["sha256"]), 64)
        self.assertEqual(record["actor"], "tester")
        self.assertEqual(record["rules_version"], support.nuclearlib.KIT_VERSION)
        self.assertEqual(len(record["kit_sha256"]), 64)
        self.assertTrue(list(self.state.glob("*.jsonl")))

    def test_chain_links_and_verifies(self) -> None:
        first = append(self.log, 1)
        second = append(self.log, 2)
        third = append(self.log, 3, phase="intent")
        self.assertEqual(second["prev_sha256"], first["sha256"])
        self.assertEqual(third["prev_sha256"], second["sha256"])
        self.assertEqual(third["seq"], 3)
        result = audit.verify(self.state)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["head"], third["sha256"])

    def test_tampered_record_is_detected(self) -> None:
        append(self.log, 1)
        append(self.log, 2)
        append(self.log, 3)
        files, lines = read_lines(self.root)
        record = json.loads(lines[1])
        record["ok"] = True
        lines[1] = json.dumps(record, ensure_ascii=False, sort_keys=True)
        files[0].write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = audit.verify(self.state)
        self.assertFalse(result["ok"])
        self.assertTrue(any("哈希不匹配" in item for item in result["errors"]))

    def test_deleted_middle_record_is_detected(self) -> None:
        for index in range(3):
            append(self.log, index)
        files, lines = read_lines(self.root)
        files[0].write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        result = audit.verify(self.state)
        self.assertFalse(result["ok"])
        self.assertTrue(any("序号不连续" in item or "链断裂" in item for item in result["errors"]))

    def test_tail_truncation_is_detected_by_state_file(self) -> None:
        for index in range(3):
            append(self.log, index)
        files, lines = read_lines(self.root)
        files[0].write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        result = audit.verify(self.state)
        self.assertFalse(result["ok"])
        self.assertTrue(any("尾部不一致" in item for item in result["errors"]))

    def test_missing_state_is_reconstructed_from_log(self) -> None:
        first = append(self.log, 1)
        second = append(self.log, 2)
        (self.state / audit.STATE_FILE).unlink()
        third = append(self.log, 3)
        self.assertEqual(third["seq"], 3)
        self.assertEqual(third["prev_sha256"], second["sha256"])
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_head_and_statement_hint(self) -> None:
        append(self.log, 1)
        last = append(self.log, 2)
        head = audit.current_head(self.state)
        self.assertEqual(head["seq"], 2)
        self.assertEqual(head["head"], last["sha256"])
        self.assertIn("audit_head=", audit.statement_hint(head))

    def test_file_sink_receives_copy(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            sink_path = Path(other) / "audit-sink.jsonl"
            log = make_log(self.root, sinks=[{"type": "file", "path": str(sink_path)}])
            append(log, 1)
            lines = sink_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["seq"], 1)

    def test_sink_failure_raises(self) -> None:
        blocker = self.root / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        log = make_log(self.root, sinks=[{"type": "file", "path": str(blocker / "audit.jsonl")}])
        with self.assertRaises(audit.AuditError):
            append(log)


class SinkConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_file_sink_inside_workspace_is_rejected(self) -> None:
        with self.assertRaises(audit.AuditError):
            audit.build_sinks([str(self.root / "audit.jsonl")], None, [self.root])

    def test_plain_http_to_remote_is_rejected(self) -> None:
        with self.assertRaises(audit.AuditError):
            audit.build_sinks(["http://example.com/audit"], None, [self.root])

    def test_loopback_http_is_allowed(self) -> None:
        sinks = audit.build_sinks(["http://127.0.0.1:9999/audit"], None, [self.root])
        self.assertEqual(sinks[0]["type"], "https")

    def test_token_file_is_read(self) -> None:
        token = self.root / "token.txt"
        token.write_text("secret-token\n", encoding="utf-8")
        sinks = audit.build_sinks(["https://example.com/audit"], str(token), [self.root])
        self.assertEqual(sinks[0]["token"], "secret-token")


class ConcurrencyTest(unittest.TestCase):
    SCRIPT = (
        "import os, sys\n"
        "sys.path.insert(0, os.environ['NUCLEAR_SCRIPTS'])\n"
        "from pathlib import Path\n"
        "from nuclearproto.audit import AuditLog\n"
        "log = AuditLog(Path(sys.argv[1]))\n"
        "for index in range(5):\n"
        "    log.append(tool='concurrent', workspace='ws', project_path='/p',"
        " arguments={'i': index}, phase='result')\n"
    )

    def test_two_processes_keep_chain_continuous(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / ".nuclear-dev" / "audit"
            env = support.child_env()
            env["NUCLEAR_SCRIPTS"] = str(support.SCRIPTS)
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", self.SCRIPT, str(state)],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(2)
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, stderr.decode("utf-8", "replace"))
            result = audit.verify(state)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["records"], 10)
            seqs = []
            for path in sorted(state.glob("*.jsonl")):
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        seqs.append(json.loads(line)["seq"])
            self.assertEqual(sorted(seqs), list(range(1, 11)))


class AuditCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = make_log(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_cli(self, *argv):
        completed = support.run_script(support.AUDIT, ["--root", str(self.root)] + list(argv))
        return completed

    def test_head_prints_chain_head(self) -> None:
        last = append(self.log, 1)
        completed = self.run_cli("head", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = support.parse_json(completed.stdout)
        self.assertEqual(payload["head"], last["sha256"])
        self.assertEqual(payload["seq"], 1)
        self.assertIn("audit_head=", payload["statement_hint"])

    def test_verify_passes_on_clean_chain(self) -> None:
        append(self.log, 1)
        completed = self.run_cli("verify", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(support.parse_json(completed.stdout)["ok"])

    def test_verify_fails_after_tamper(self) -> None:
        append(self.log, 1)
        append(self.log, 2)
        files, lines = read_lines(self.root)
        record = json.loads(lines[0])
        record["tool"] = "forged"
        lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True)
        files[0].write_text("\n".join(lines) + "\n", encoding="utf-8")
        completed = self.run_cli("verify", "--json")
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(support.parse_json(completed.stdout)["ok"])

    def test_verify_on_empty_project_succeeds(self) -> None:
        completed = self.run_cli("verify", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = support.parse_json(completed.stdout)
        self.assertEqual(payload["records"], 0)


if __name__ == "__main__":
    unittest.main()
