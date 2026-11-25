#!/usr/bin/env python3
"""领域参考与 `nuclearctl domain` 只读命令的回归测试。

领域参考是工程指导，不参与门禁判定；这里锁定它们存在、可机读、与索引一致，
且不会把占位字符串混进领域文档。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

REFS = support.REPO / "skills" / "nuclear-dev" / "references"
CTL = support.CTL
STAGES = support.STAGES

# 与 domain-index.md 及 nuclearctl.command_domain 的目录保持一致。
DOMAIN_FILES = {
    "plan": ["safety-classification.md", "nuclear-standards.md"],
    "requirements": ["physical-models.md", "nuclear-data.md", "requirement-patterns.md"],
    "design": ["numerical-methods.md", "discretization-conservation.md", "parallel-design.md"],
    "implementation": ["hpc-implementation.md", "reproducible-builds.md"],
    "test": ["test-patterns.md", "benchmark-catalog.md"],
    "vv": ["vv-methods.md", "uncertainty-quantification.md"],
    "release": ["configuration-and-data-freeze.md"],
}
PLACEHOLDERS = ("TBD", "TODO", "UNKNOWN", "DRAFT", "PENDING")


class DomainReferencesTest(unittest.TestCase):
    def test_every_stage_has_reference_documents(self) -> None:
        self.assertEqual(sorted(DOMAIN_FILES), sorted(STAGES))
        for stage, names in DOMAIN_FILES.items():
            self.assertTrue(names, "%s 没有领域参考" % stage)
            for name in names:
                path = REFS / name
                self.assertTrue(path.is_file(), "缺少 %s 的领域参考 %s" % (stage, name))
                raw = path.read_bytes()
                self.assertNotIn(b"\r\n", raw, "%s 含 CRLF" % name)
                text = raw.decode("utf-8")
                self.assertTrue(text.startswith("# "), "%s 缺少标题" % name)
                # Schema 状态值（如 `pending`）总在反引号内，是合法讨论；只检查正文里的裸占位值。
                prose = __import__("re").sub(r"`[^`]*`", "", text).upper()
                for token in PLACEHOLDERS:
                    self.assertNotIn(token, prose, "%s 含裸占位值 %s" % (name, token))

    def test_index_lists_every_reference(self) -> None:
        index = (REFS / "domain-index.md").read_text(encoding="utf-8")
        for stage, names in DOMAIN_FILES.items():
            self.assertIn(stage, index)
            for name in names:
                self.assertIn(name, index, "domain-index.md 未列出 %s" % name)

    def test_domain_command_lists_readable_references(self) -> None:
        for stage in STAGES:
            completed = support.run_script(CTL, ["--root", str(support.REPO), "domain", stage, "--json"])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["stage"], stage)
            self.assertTrue(payload["advisory_only"])
            self.assertTrue(payload["summary"])
            names = [item["name"] for item in payload["references"]]
            self.assertEqual(names, DOMAIN_FILES[stage], "domain 命令与索引不一致: %s" % stage)
            self.assertTrue(all(item["exists"] for item in payload["references"]))
            self.assertTrue(Path(payload["index"]).is_file())

    def test_domain_command_works_before_init_and_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = support.run_script(CTL, ["--root", temp, "domain", "vv", "--json"])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["stage"], "vv")
        completed = support.run_script(CTL, ["--root", str(support.REPO), "domain", "bogus", "--json"])
        self.assertEqual(completed.returncode, 2)

    def test_domain_docs_carry_source_tier_disclaimer(self) -> None:
        for stage, names in DOMAIN_FILES.items():
            for name in names:
                text = (REFS / name).read_text(encoding="utf-8")
                self.assertIn("不参与门禁判定", text, "%s 缺少免责声明" % name)
                self.assertIn("参考性材料", text, "%s 未标注参考性" % name)


if __name__ == "__main__":
    unittest.main()
