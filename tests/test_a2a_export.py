#!/usr/bin/env python3
"""导出策略、投影包、双人特批与一次性令牌的回归测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support

from nuclearproto import a2a_export, a2a_policy, a2a_projection


def now_iso(offset_seconds: int = 0) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_policy(project: Path, allow_c3: bool = True, max_class: str = "C3") -> None:
    payload = {
        "schema_version": 1,
        "default": "deny",
        "recipients": {
            "vv-org": {
                "organization": "示例 V&V 组织",
                "max_class": max_class,
                "projections": ["requirements", "design_summary", "test_summary", "vv_scope"],
                "allow_c3_raw": allow_c3,
                "scope_label": "高完整性等级 A",
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_classification(project: Path, entries) -> None:
    path = project / ".nuclear-dev" / "a2a" / "classification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "entries": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_exp(project: Path, files, approvers=None, expires_at=None, recipient_org="示例 V&V 组织"):
    record = {
        "schema_version": 1,
        "id": "EXP-001",
        "purpose": "白盒代码验证",
        "recipient": {"agent_id": "vv-org", "organization": recipient_org},
        "expires_at": expires_at or now_iso(86400),
        "files": files,
        "approvers": approvers
        if approvers is not None
        else [
            {
                "name": "张三",
                "role": "data_owner",
                "organization": "开发组织",
                "actor_type": "human",
                "signed_at": now_iso(),
            },
            {
                "name": "李四",
                "role": "security_officer",
                "organization": "安全组织",
                "actor_type": "human",
                "signed_at": now_iso(),
            },
        ],
        "statement": "同意在约定用途范围内导出。",
    }
    directory = a2a_export.export_approvals_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "EXP-001.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        support.build_valid_project(self.root)
        write_policy(self.root)
        write_classification(
            self.root,
            [
                {"path": "src/solver.py", "class": "C3", "transferable": True},
                {"path": "release/sbom.json", "class": "C2", "transferable": True},
                {"path": "benchmark/data.csv", "class": "C3", "transferable": False},
            ],
        )
        support.write_text(self.root / "benchmark" / "data.csv", "x,y\n1,2\n")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_load_and_recipient(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        self.assertEqual(policy.recipient("vv-org")["organization"], "示例 V&V 组织")
        self.assertTrue(policy.projection_allowed("requirements", "vv-org"))
        self.assertFalse(policy.projection_allowed("design_summary", "read-only-org"))

    def test_unknown_recipient_is_denied(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        with self.assertRaises(a2a_policy.PolicyError):
            policy.recipient("unknown-org")

    def test_missing_policy_denies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(a2a_policy.PolicyError):
                a2a_policy.ExportPolicy.load(Path(temp))

    def test_forbidden_paths_are_denied(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        for relative in [
            ".nuclear-dev/approvals/plan.json",
            ".nuclear-dev/audit/2026-10-26.jsonl",
            ".nuclear-dev/evidence/provenance.json",
        ]:
            with self.assertRaises(a2a_policy.PolicyError):
                policy.classify(relative)

    def test_unclassified_file_is_not_transferable(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        entry = policy.classify("notes/unknown.txt")
        self.assertEqual(entry["class"], "C3")
        self.assertFalse(entry["transferable"])

    def test_non_transferable_file_blocks_export(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        with self.assertRaises(a2a_policy.PolicyError):
            policy.assert_raw_exportable("benchmark/data.csv", "vv-org")

    def test_c2_file_cannot_be_exported_raw(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        with self.assertRaises(a2a_policy.PolicyError):
            policy.assert_raw_exportable("release/sbom.json", "vv-org")

    def test_recipient_without_c3_cannot_export_raw(self) -> None:
        policy = a2a_policy.ExportPolicy.load(self.root)
        with self.assertRaises(a2a_policy.PolicyError):
            policy.assert_raw_exportable("src/solver.py", "read-only-org")


class ProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        support.build_valid_project(self.root)
        write_policy(self.root)
        write_classification(
            self.root,
            [
                {"path": "src/solver.py", "class": "C3", "transferable": True},
                {"path": "release/sbom.json", "class": "C2", "transferable": True},
            ],
        )
        self.policy = a2a_policy.ExportPolicy.load(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_build_and_verify_bundle(self) -> None:
        result = a2a_projection.build_bundle(self.root, "vv-org", self.policy)
        self.assertTrue(result["bundle_dir"].is_dir())
        verification = a2a_projection.verify_bundle(result["bundle_dir"])
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertEqual(verification["digest"], result["digest"])
        manifest = result["manifest"]
        self.assertEqual(manifest["recipient"]["organization"], "示例 V&V 组织")
        self.assertEqual(manifest["recipient"]["scope_label"], "高完整性等级 A")
        self.assertEqual(len(manifest["projections"]), 4)

    def test_requirements_projection_drops_sensitive_fields(self) -> None:
        result = a2a_projection.build_bundle(self.root, "vv-org", self.policy, projections=["requirements"])
        payload = json.loads((result["bundle_dir"] / "requirements.json").read_text(encoding="utf-8"))
        item = payload["items"][0]
        for key in ("rationale", "safety_class", "source", "status", "interfaces"):
            self.assertNotIn(key, item)

    def test_design_summary_drops_equations(self) -> None:
        result = a2a_projection.build_bundle(
            self.root, "vv-org", self.policy, projections=["design_summary"]
        )
        text = (result["bundle_dir"] / "design-summary.md").read_text(encoding="utf-8")
        self.assertIn("MDL-001", text)
        self.assertNotIn("d/dx", text)

    def test_test_summary_drops_procedure(self) -> None:
        result = a2a_projection.build_bundle(
            self.root, "vv-org", self.policy, projections=["test_summary"]
        )
        payload = json.loads((result["bundle_dir"] / "test-summary.json").read_text(encoding="utf-8"))
        for test in payload["tests"]:
            self.assertNotIn("procedure", test)
            self.assertNotIn("actual", test)

    def test_projection_not_allowed_is_rejected(self) -> None:
        with self.assertRaises(a2a_policy.PolicyError):
            a2a_projection.build_bundle(
                self.root, "read-only-org", self.policy, projections=["design_summary"]
            )

    def test_extra_file_is_detected(self) -> None:
        result = a2a_projection.build_bundle(self.root, "vv-org", self.policy)
        support.write_text(result["bundle_dir"] / "extra.txt", "extra\n")
        verification = a2a_projection.verify_bundle(result["bundle_dir"])
        self.assertFalse(verification["ok"])
        self.assertTrue(any("清单外文件" in item for item in verification["errors"]))

    def test_manifest_tamper_is_detected(self) -> None:
        result = a2a_projection.build_bundle(self.root, "vv-org", self.policy)
        manifest_path = result["bundle_dir"] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["recipient"]["organization"] = "伪造组织"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verification = a2a_projection.verify_bundle(result["bundle_dir"])
        self.assertFalse(verification["ok"])
        self.assertTrue(any("摘要不匹配" in item for item in verification["errors"]))


class ExportAuthorizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        support.build_valid_project(self.root)
        write_policy(self.root)
        write_classification(
            self.root,
            [
                {"path": "src/solver.py", "class": "C3", "transferable": True},
                {"path": "benchmark/data.csv", "class": "C3", "transferable": False},
            ],
        )
        support.write_text(self.root / "benchmark" / "data.csv", "x,y\n1,2\n")
        self.policy = a2a_policy.ExportPolicy.load(self.root)
        self.bundle = a2a_projection.build_bundle(self.root, "vv-org", self.policy)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_c2_bundle_token_roundtrip(self) -> None:
        record = a2a_export.create_authorization(
            self.root, self.bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )
        self.assertEqual(record["max_class"], "C2")
        consumed = a2a_export.consume_authorization(
            self.root, record["token_id"], self.bundle["bundle_dir"], "vv-org"
        )
        self.assertIsNotNone(consumed["used_at"])
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.consume_authorization(
                self.root, record["token_id"], self.bundle["bundle_dir"], "vv-org"
            )

    def test_token_bound_to_bundle_digest(self) -> None:
        record = a2a_export.create_authorization(
            self.root, self.bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )
        other = a2a_projection.build_bundle(self.root, "vv-org", self.policy)
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.consume_authorization(
                self.root, record["token_id"], other["bundle_dir"], "vv-org"
            )

    def test_expired_token_is_rejected(self) -> None:
        record = a2a_export.create_authorization(
            self.root, self.bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )
        path = a2a_export.authorizations_dir(self.root) / (record["token_id"] + ".json")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["expires_at"] = now_iso(-10)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.consume_authorization(
                self.root, record["token_id"], self.bundle["bundle_dir"], "vv-org"
            )

    def test_raw_export_requires_dual_approval(self) -> None:
        entries = [
            {
                "path": "src/solver.py",
                "sha256": support.sha256_file(self.root / "src" / "solver.py"),
            }
        ]
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.cover_raw_entries(entries, [])
        write_exp(
            self.root,
            [{"path": "src/solver.py", "sha256": entries[0]["sha256"], "class": "C3"}],
            approvers=[
                {
                    "name": "张三",
                    "role": "data_owner",
                    "organization": "开发组织",
                    "actor_type": "human",
                    "signed_at": now_iso(),
                }
            ],
        )
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.load_export_approvals(self.root, "vv-org", self.policy)

    def test_valid_dual_approval_allows_raw_export(self) -> None:
        digest = support.sha256_file(self.root / "src" / "solver.py")
        write_exp(
            self.root,
            [{"path": "src/solver.py", "sha256": digest, "class": "C3"}],
        )
        approvals = a2a_export.load_export_approvals(self.root, "vv-org", self.policy)
        covered = a2a_export.cover_raw_entries(
            [{"path": "src/solver.py", "sha256": digest}], approvals
        )
        self.assertEqual(covered[0]["authorization_id"], "EXP-001")
        bundle = a2a_projection.build_bundle(
            self.root, "vv-org", self.policy, raw_entries=covered
        )
        verification = a2a_projection.verify_bundle(bundle["bundle_dir"])
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertEqual(verification["manifest"]["raw_files"][0]["class"], "C3")
        token = a2a_export.create_authorization(
            self.root, bundle["bundle_dir"], "项目负责人", recipient_name="vv-org"
        )
        self.assertEqual(token["max_class"], "C3")

    def test_non_transferable_file_blocks_even_with_approval(self) -> None:
        digest = support.sha256_file(self.root / "benchmark" / "data.csv")
        write_exp(
            self.root,
            [{"path": "benchmark/data.csv", "sha256": digest, "class": "C3"}],
        )
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.load_export_approvals(self.root, "vv-org", self.policy)

    def test_approvers_must_be_distinct_people_and_orgs(self) -> None:
        digest = support.sha256_file(self.root / "src" / "solver.py")
        same = [
            {
                "name": "张三",
                "role": "data_owner",
                "organization": "开发组织",
                "actor_type": "human",
                "signed_at": now_iso(),
            },
            {
                "name": "张三",
                "role": "security_officer",
                "organization": "安全组织",
                "actor_type": "human",
                "signed_at": now_iso(),
            },
        ]
        write_exp(self.root, [{"path": "src/solver.py", "sha256": digest, "class": "C3"}], approvers=same)
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.load_export_approvals(self.root, "vv-org", self.policy)

    def test_hash_mismatch_is_rejected(self) -> None:
        write_exp(
            self.root,
            [{"path": "src/solver.py", "sha256": "0" * 64, "class": "C3"}],
        )
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.load_export_approvals(self.root, "vv-org", self.policy)

    def test_expired_approval_is_rejected(self) -> None:
        digest = support.sha256_file(self.root / "src" / "solver.py")
        write_exp(
            self.root,
            [{"path": "src/solver.py", "sha256": digest, "class": "C3"}],
            expires_at=now_iso(-10),
        )
        with self.assertRaises(a2a_export.ExportError):
            a2a_export.load_export_approvals(self.root, "vv-org", self.policy)


if __name__ == "__main__":
    unittest.main()
