#!/usr/bin/env python3
"""七阶段门禁的正向与负向回归测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support


class GatePositiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_all_stages_pass_with_dependencies(self) -> None:
        for stage in support.STAGES:
            code, payload, err = support.ctl(self.root, "gate", stage, "--json")
            self.assertEqual(code, 0, "%s: %s %s" % (stage, err, payload.get("errors")))

    def test_status_reports_every_stage_passed(self) -> None:
        code, payload, err = support.ctl(self.root, "status", "--json")
        self.assertEqual(code, 0, err)
        for stage, record in payload["stages"].items():
            self.assertTrue(record["passed"], "%s: %s" % (stage, record["errors"]))

    def test_validate_passes(self) -> None:
        code, payload, err = support.ctl(self.root, "validate", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["errors"], [])

    def test_gate_without_dependencies_passes(self) -> None:
        code, payload, err = support.ctl(self.root, "gate", "release", "--no-dependencies", "--json")
        self.assertEqual(code, 0, "%s %s" % (err, payload.get("errors")))

    def test_manifest_is_deterministic_and_version_checked(self) -> None:
        code, payload, err = support.ctl(self.root, "manifest", "--version", "1.0.0", "--json")
        self.assertEqual(code, 0, err)
        destination = Path(payload["path"])
        self.assertTrue(destination.is_file())
        first = support.sha256_file(destination)
        code, _, err = support.ctl(self.root, "manifest", "--version", "1.0.0", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(support.sha256_file(destination), first)
        code, _, err = support.ctl(self.root, "manifest", "--version", "2.0.0", "--json")
        self.assertEqual(code, 2)
        self.assertIn("版本不匹配", err)


class GateNegativeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def assert_blocks(self, stage: str, expected: str) -> None:
        code, payload, _ = support.ctl(self.root, "gate", stage, "--json")
        self.assertEqual(code, 1, payload.get("errors"))
        joined = "\n".join(payload["errors"])
        self.assertIn(expected, joined)

    def test_plan_placeholder_blocks(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"],
            lambda value: value["project"].__setitem__("purpose", "TBD"),
        )
        self.assert_blocks("plan", "未完成占位值")

    def test_unclosed_open_item_blocks(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"],
            lambda value: value["open_items"].append(
                {"id": "OI-001", "description": "待确认的适用标准", "status": "open", "owner": "张三"}
            ),
        )
        self.assert_blocks("plan", "未关闭事项")

    def test_dirty_source_control_blocks(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["implementation"],
            lambda value: value["source_control"].__setitem__("dirty", True),
        )
        self.assert_blocks("implementation", "源码工作区必须干净")

    def test_evidence_tamper_is_detected(self) -> None:
        target = self.root / "evidence" / "build.log"
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write("tampered\n")
        code, payload, _ = support.ctl(self.root, "validate", "--json")
        self.assertEqual(code, 1)
        self.assertTrue(any("SHA256 不匹配" in item for item in payload["errors"]))
        self.assert_blocks("implementation", "SHA256 不匹配")

    def test_artifact_change_invalidates_approval(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"],
            lambda value: value["project"].__setitem__("purpose", "更新后的项目目的说明"),
        )
        self.assert_blocks("plan", "产物已变化，批准失效")

    def test_missing_approval_blocks(self) -> None:
        (self.root / ".nuclear-dev" / "approvals" / "plan.json").unlink()
        self.assert_blocks("plan", "缺少人工批准记录")

    def test_evidence_not_passed_blocks(self) -> None:
        def mark_failed(index):
            for record in index["evidence"]:
                if record["id"] == self.evidence["build"]:
                    record["result"] = "failed"

        support.mutate_json(self.root / ".nuclear-dev" / "evidence" / "index.json", mark_failed)
        self.assert_blocks("implementation", "结果不是 passed")

    def test_vv_independence_false_blocks(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["vv"],
            lambda value: value["independence"]["vv_executor"].__setitem__("independent", False),
        )
        self.assert_blocks("vv", "执行者和审核者都必须声明独立于开发方")

    def test_release_revision_mismatch_blocks(self) -> None:
        support.mutate_json(
            self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["release"],
            lambda value: value.__setitem__("source_revision", "zzz9999"),
        )
        self.assert_blocks("release", "发布版本必须与已实现源码 revision 一致")

    def test_dependency_failure_propagates_and_status_does_not_recurse(self) -> None:
        (self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"]).unlink()
        self.assert_blocks("release", "前置阶段 plan 未通过")
        code, payload, err = support.ctl(self.root, "status", "--json")
        self.assertEqual(code, 0, err)
        self.assertFalse(payload["stages"]["plan"]["passed"])
        self.assertTrue(payload["stages"]["release"]["passed"])

    def test_gate_is_read_only(self) -> None:
        snapshot = {
            path.relative_to(self.root).as_posix(): support.sha256_file(path)
            for path in sorted((self.root / ".nuclear-dev").rglob("*"))
            if path.is_file()
        }
        support.ctl(self.root, "gate", "release", "--json")
        after = {
            path.relative_to(self.root).as_posix(): support.sha256_file(path)
            for path in sorted((self.root / ".nuclear-dev").rglob("*"))
            if path.is_file()
        }
        self.assertEqual(snapshot, after)


if __name__ == "__main__":
    unittest.main()
