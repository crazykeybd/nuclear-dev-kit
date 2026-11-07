#!/usr/bin/env python3
"""工作区体检（doctor）的回归测试。

体检只读、只转述：它把环境、结构、阶段、轨迹链与审计链一次报出来，
但"体检通过"不等于"门禁通过"，也不生成任何批准。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support


def snapshot(root: Path):
    """工作区里每个文件的相对路径与摘要，用来证明体检没写过文件。"""
    return {
        path.relative_to(root).as_posix(): support.sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class DoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def doctor(self, *extra: str):
        return support.ctl(self.root, "doctor", "--json", *extra)

    def check(self, payload, identifier: str):
        for item in payload["checks"]:
            if item["id"] == identifier:
                return item
        raise AssertionError("体检结果里没有 %s 项: %s" % (identifier, payload["checks"]))


class DoctorPositiveTest(DoctorTest):
    def test_valid_workspace_is_healthy(self) -> None:
        support.build_valid_project(self.root)
        code, payload, err = self.doctor()
        self.assertEqual(code, 0, "%s %s" % (err, payload))
        self.assertTrue(payload["ok"], json.dumps(payload, ensure_ascii=False))
        self.assertEqual([item["id"] for item in payload["checks"]], ["kit", "workspace", "traces", "audit"])
        for item in payload["checks"]:
            self.assertTrue(item["ok"], item)
        self.assertEqual(len(payload["stages"]), 7)
        self.assertTrue(all(item["passed"] for item in payload["stages"]))
        self.assertIsNone(payload["next"])

    def test_report_has_no_approval_shortcut(self) -> None:
        support.build_valid_project(self.root)
        _, payload, _ = self.doctor()
        text = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("approve\"", text)
        self.assertNotIn('"approval"', text)

    def test_freshly_initialised_workspace_is_healthy(self) -> None:
        """刚初始化、一个阶段都没做的项目是完好的：未开始不等于故障。"""
        code, created, err = support.ctl(self.root, "init", "--name", "示例", "--id", "demo", "--json")
        self.assertEqual(code, 0, "%s %s" % (err, created))
        code, payload, err = self.doctor()
        self.assertEqual(code, 0, "%s %s" % (err, payload))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["next"], "plan")
        self.assertFalse(any(item["passed"] for item in payload["stages"]))

    def test_doctor_writes_nothing(self) -> None:
        support.build_valid_project(self.root)
        support.ctl(self.root, "gate", "plan", "--trace", "--json")
        before = snapshot(self.root)
        code, _, err = self.doctor()
        self.assertEqual(code, 0, err)
        support.ctl(self.root, "doctor")
        self.assertEqual(snapshot(self.root), before)

    def test_human_output_names_the_next_stage(self) -> None:
        support.build_valid_project(self.root)
        support.mutate_json(
            self.root / ".nuclear-dev" / "stages" / "test" / "test-report.json",
            lambda value: value["tests"][0].update({"result": "failed"}),
        )
        completed = support.run_script(support.CTL, ["--root", str(self.root), "doctor"])
        self.assertEqual(completed.returncode, 1, "失败的测试结果必须让体检不通过")
        self.assertIn("阶段进展: 6/7 通过", completed.stdout)
        self.assertIn("下一步: 阶段 test", completed.stdout)


class DoctorNegativeTest(DoctorTest):
    def test_uninitialised_workspace_is_reported(self) -> None:
        code, payload, err = self.doctor()
        self.assertEqual(code, 1, err)
        self.assertFalse(payload["ok"])
        workspace = self.check(payload, "workspace")
        self.assertFalse(workspace["ok"])
        self.assertTrue(any("未初始化" in item for item in workspace["errors"]))
        self.assertTrue(payload["next"])

    def test_tampered_evidence_is_reported(self) -> None:
        support.build_valid_project(self.root)
        evidence = self.root / "evidence" / "unit.log"
        support.write_text(evidence, "证据被改过了\n")
        code, payload, err = self.doctor()
        self.assertEqual(code, 1, err)
        self.assertFalse(payload["ok"])
        self.assertFalse(self.check(payload, "workspace")["ok"])

    def test_broken_trace_chain_is_reported(self) -> None:
        support.build_valid_project(self.root)
        code, traced, err = support.ctl(self.root, "gate", "plan", "--trace", "--json")
        self.assertEqual(code, 0, err)
        path = self.root / traced["trace"]["path"]
        record = json.loads(path.read_text(encoding="utf-8"))
        record["verdict"]["errors"] = ["被改写成别的话"]
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        code, payload, err = self.doctor()
        self.assertEqual(code, 1, err)
        traces = self.check(payload, "traces")
        self.assertFalse(traces["ok"])
        self.assertEqual(traces["detail"]["count"], 1)

    def test_drift_is_shown_but_not_a_failure(self) -> None:
        support.build_valid_project(self.root)
        support.ctl(self.root, "gate", "plan", "--trace", "--json")
        support.mutate_json(
            self.root / ".nuclear-dev" / "stages" / "plan" / "plan.json",
            lambda value: value["project"].update({"name": "改过的名字"}),
        )
        code, payload, err = self.doctor()
        traces = self.check(payload, "traces")
        self.assertEqual(len(traces["detail"]["drift"]), 1)
        # 产物被改过，批准失效，所以 workspace 那一项会失败；轨迹链本身仍然自洽。
        self.assertTrue(traces["ok"])
        self.assertEqual(code, 1, err)


class DoctorHelpTest(unittest.TestCase):
    def test_help_lists_the_command(self) -> None:
        completed = support.run_script(support.CTL, ["--help"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("doctor", completed.stdout)
        self.assertIn("trace", completed.stdout)


if __name__ == "__main__":
    unittest.main()
