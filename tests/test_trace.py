#!/usr/bin/env python3
"""门禁运行轨迹（trace）的回归测试。

轨迹的标准见 skills/nuclear-dev/references/tracing.md。这些用例锁定三件事：
判定结论与轨迹是否写成互不影响、轨迹链可校验、产物变化只报偏离不算篡改。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

TRACES = "traces"


class TraceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)
        self.traces = self.root / ".nuclear-dev" / TRACES

    def tearDown(self) -> None:
        self._temp.cleanup()

    def trace_files(self):
        return sorted(self.traces.glob("TRC-*.json"))

    def gate(self, stage: str, *extra: str):
        return support.ctl(self.root, "gate", stage, "--json", *extra)


class TraceRecordingTest(TraceCase):
    def test_gate_without_the_flag_records_nothing(self) -> None:
        code, payload, err = self.gate("design")
        self.assertEqual(code, 0, err)
        self.assertNotIn("trace", payload)
        self.assertFalse(self.traces.exists())

    def test_flag_records_the_verdict(self) -> None:
        code, payload, err = self.gate("design", "--trace")
        self.assertEqual(code, 0, err)
        trace = payload["trace"]
        self.assertTrue(trace["ok"], trace)
        path = self.root / trace["path"]
        self.assertTrue(path.is_file())
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["trace_id"], trace["trace_id"])
        self.assertEqual(record["kind"], "gate")
        self.assertEqual(record["stage"], "design")
        self.assertEqual(record["verdict"], {"ok": True, "errors": []})
        self.assertEqual(record["sequence"], 1)
        self.assertEqual(record["prev_record_sha256"], "0" * 64)
        for field in ("environment", "spans", "artifacts", "started_at", "finished_at", "duration_ms", "record_sha256"):
            self.assertIn(field, record)
        self.assertEqual(record["environment"]["kit_version"], support.nuclearlib.KIT_VERSION)

    def test_spans_cover_the_stages_the_gate_examined(self) -> None:
        code, payload, err = self.gate("requirements", "--trace")
        self.assertEqual(code, 0, err)
        record = json.loads((self.root / payload["trace"]["path"]).read_text(encoding="utf-8"))
        names = [span["name"] for span in record["spans"]]
        self.assertEqual(names[0], "gate.requirements")
        self.assertEqual(names[1:], ["stage.check.plan", "stage.check.requirements"])
        root_span = record["spans"][0]
        self.assertIsNone(root_span["parent_span_id"])
        for span in record["spans"][1:]:
            self.assertEqual(span["parent_span_id"], root_span["span_id"])
            self.assertEqual(span["status"], "ok")

    def test_artifacts_cover_only_examined_stages(self) -> None:
        code, payload, err = self.gate("design", "--trace")
        self.assertEqual(code, 0, err)
        record = json.loads((self.root / payload["trace"]["path"]).read_text(encoding="utf-8"))
        stages = {item["stage"] for item in record["artifacts"]}
        self.assertEqual(stages, {"plan", "requirements", "design"})
        for item in record["artifacts"]:
            self.assertTrue(item["present"])
            self.assertEqual(len(item["sha256"]), 64)

    def test_blocked_gate_is_recorded_verbatim(self) -> None:
        support.write_text(self.root / ".nuclear-dev" / "stages" / "plan" / "plan.json", "{}\n")
        code, payload, err = self.gate("plan", "--trace")
        self.assertEqual(code, 1, err)
        self.assertTrue(payload.get("trace", {}).get("ok"), payload.get("trace"))
        record = json.loads((self.root / payload["trace"]["path"]).read_text(encoding="utf-8"))
        self.assertFalse(record["verdict"]["ok"])
        self.assertTrue(record["verdict"]["errors"])
        self.assertEqual(record["verdict"]["errors"], payload["errors"])

    def test_environment_variable_enables_tracing(self) -> None:
        env = dict(support.child_env())
        env["NUCLEAR_DEV_TRACE"] = "1"
        completed = support.run_script(
            support.CTL, ["--root", str(self.root), "gate", "plan", "--json"], env=env
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(support.parse_json(completed.stdout)["trace"]["ok"])
        self.assertTrue(self.trace_files())

    def test_trace_failure_leaves_the_verdict_alone(self) -> None:
        """轨迹目录位置被一个文件占住时，门禁结论与退出码都不许变。"""
        support.write_text(self.root / ".nuclear-dev" / TRACES, "占位文件，不是目录\n")
        code, payload, err = self.gate("plan", "--trace")
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])
        self.assertFalse(payload["trace"]["ok"])
        self.assertIn("运行轨迹未写成", err)


class TraceChainTest(TraceCase):
    def record(self, *stages: str):
        for stage in stages:
            code, payload, err = self.gate(stage, "--trace")
            self.assertEqual(code, 0, "%s: %s" % (stage, err))
        return self.trace_files()

    def test_records_are_chained_in_order(self) -> None:
        files = self.record("plan", "requirements", "design")
        self.assertEqual(len(files), 3)
        records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        records.sort(key=lambda item: item["sequence"])
        self.assertEqual([item["sequence"] for item in records], [1, 2, 3])
        self.assertEqual(records[1]["prev_record_sha256"], records[0]["record_sha256"])
        self.assertEqual(records[2]["prev_record_sha256"], records[1]["record_sha256"])
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 0, "%s %s" % (err, payload))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["traces"], 3)
        self.assertEqual(payload["head"], records[2]["record_sha256"])

    def test_list_shows_newest_first(self) -> None:
        self.record("plan", "requirements")
        code, payload, err = support.ctl(self.root, "trace", "list", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual([item["sequence"] for item in payload["traces"]], [2, 1])
        self.assertEqual([item["stage"] for item in payload["traces"]], ["requirements", "plan"])

    def test_list_limit(self) -> None:
        self.record("plan", "requirements", "design")
        code, payload, err = support.ctl(self.root, "trace", "list", "--limit", "1", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(payload["traces"]), 1)
        self.assertEqual(payload["traces"][0]["sequence"], 3)

    def test_show_returns_the_record(self) -> None:
        files = self.record("plan")
        trace_id = files[0].name[: -len(".json")]
        code, payload, err = support.ctl(self.root, "trace", "show", trace_id, "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["trace"]["trace_id"], trace_id)

    def test_show_rejects_unknown_and_traversal_ids(self) -> None:
        self.record("plan")
        code, _, err = support.ctl(self.root, "trace", "show", "TRC-不存在", "--json")
        self.assertEqual(code, 2)
        self.assertIn("轨迹不存在", err)
        code, _, err = support.ctl(self.root, "trace", "show", "../project", "--json")
        self.assertEqual(code, 2)
        self.assertIn("轨迹标识无效", err)

    def test_tampered_record_fails_verification(self) -> None:
        files = self.record("plan")
        record = json.loads(files[0].read_text(encoding="utf-8"))
        record["verdict"]["errors"] = ["被改写成别的话"]
        files[0].write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 1, err)
        self.assertFalse(payload["ok"])
        self.assertTrue(any("摘要自校验失败" in item for item in payload["errors"]))

    def test_missing_record_fails_verification(self) -> None:
        files = self.record("plan", "requirements", "design")
        middle = [path for path in files if json.loads(path.read_text(encoding="utf-8"))["sequence"] == 2]
        self.assertEqual(len(middle), 1)
        middle[0].unlink()
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 1, err)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["errors"])

    def test_artifact_change_is_reported_as_drift_only(self) -> None:
        self.record("design")
        support.mutate_json(
            self.artifact_path("design"),
            lambda value: value["architecture"].update({"overview": "改过的架构说明"}),
        )
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 0, "%s %s" % (err, payload))
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["drift"]), 1)
        self.assertEqual(payload["drift"][0]["state"], "changed")
        self.assertEqual(payload["drift"][0]["path"], "stages/design/design.json")

    def test_removed_artifact_is_reported_as_drift(self) -> None:
        self.record("design")
        self.artifact_path("design").unlink()
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["drift"][0]["state"], "removed")

    def test_verify_without_traces_is_clean(self) -> None:
        code, payload, err = support.ctl(self.root, "trace", "verify", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["traces"], 0)
        self.assertEqual(payload["head"], "0" * 64)

    def artifact_path(self, stage: str) -> Path:
        return self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS[stage]


class TraceHelpTest(unittest.TestCase):
    def test_trace_needs_a_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = support.run_script(support.CTL, ["--root", temp, "trace"])
        self.assertEqual(completed.returncode, 2)
        self.assertIn("trace 需要子命令", completed.stderr)


if __name__ == "__main__":
    unittest.main()
