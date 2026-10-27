#!/usr/bin/env python3
"""catalog.json 生成器的回归测试。

catalog.json 是 SKILL.md frontmatter 与冻结内核的确定性投影：
同一源必须得到同一字节序列，源变化而未重新生成时测试必须失败。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

GEN_CATALOG = support.REPO / "tools" / "gen_catalog.py"
CATALOG = support.REPO / "catalog.json"


class CatalogTest(unittest.TestCase):
    def test_catalog_is_up_to_date(self) -> None:
        completed = support.run_script(GEN_CATALOG, ["--check"])
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_catalog_matches_kernel(self) -> None:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(data["kit"]["version"], support.nuclearlib.KIT_VERSION)
        self.assertEqual(data["kit"]["schema_version"], support.nuclearlib.SCHEMA_VERSION)
        self.assertEqual([item["name"] for item in data["stages"]], support.nuclearlib.STAGES)
        self.assertEqual(
            [item["artifact"] for item in data["stages"]],
            [support.nuclearlib.STAGE_ARTIFACTS[stage] for stage in support.nuclearlib.STAGES],
        )
        self.assertEqual(len(data["skills"]), 10)
        self.assertEqual(len(data["mcp"]["tools"]), 6)
        self.assertEqual(len(data["mcp"]["write_tools"]), 4)
        self.assertNotIn("approve", json.dumps(data, ensure_ascii=False).lower())

    def test_generation_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "one.json"
            second = Path(temp) / "two.json"
            for target in (first, second):
                completed = support.run_script(GEN_CATALOG, ["--output", str(target)])
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.read_bytes(), CATALOG.read_bytes())

    def test_check_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stale = Path(temp) / "stale.json"
            stale.write_text("{}\n", encoding="utf-8")
            completed = support.run_script(GEN_CATALOG, ["--check", "--output", str(stale)])
        self.assertEqual(completed.returncode, 1)
        self.assertIn("已过期", completed.stderr)


if __name__ == "__main__":
    unittest.main()
