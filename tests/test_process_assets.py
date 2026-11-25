#!/usr/bin/env python3
"""process-assets 独立包的回归测试。

锁定：40 个 Skill 由源导出确定性生成、frontmatter 合规、阶段映射完整、
assetctl 只读查询可用；不触碰核心 10 个 Skill 与门禁判定。
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import support

REPO = support.REPO
PA = REPO / "process-assets"
SKILLS = PA / "skills"
SOURCE = Path("/home/Admin/Desktop/资产库.md")
SPLIT = REPO / "tools" / "split_process_assets.py"
CTL = PA / "scripts" / "assetctl.py"
INSTALL = PA / "scripts" / "install.py"
STAGES = support.STAGES
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class ProcessAssetsTest(unittest.TestCase):
    def test_all_skills_present_and_within_limits(self) -> None:
        files = sorted(SKILLS.glob("*/SKILL.md"))
        self.assertEqual(len(files), 40)
        for path in files:
            raw = path.read_bytes()
            self.assertLessEqual(len(raw), 8192, "%s 超 8KB" % path)
            self.assertNotIn(b"\r\n", raw, "%s 含 CRLF" % path)
            text = raw.decode("utf-8")
            self.assertTrue(text.startswith("---\n"))
            name = re.search(r"^name: (.+)$", text, re.M).group(1)
            self.assertRegex(name, NAME_RE)
            self.assertEqual(name, path.parent.name)

    def test_split_is_reproducible_and_matches_source(self) -> None:
        if not SOURCE.is_file():
            self.skipTest("源导出文件不在本机，跳过重建一致性检查")
        completed = support.run_script(SPLIT, ["--check"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("40 个 Skill", completed.stdout)

    def test_every_skill_has_stage_and_description(self) -> None:
        stages = set(STAGES) | {"router"}
        for path in sorted(SKILLS.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            stage = re.search(r'^  stage: "(.+)"$', text, re.M)
            self.assertIsNotNone(stage, "%s 缺 stage" % path)
            self.assertIn(stage.group(1), stages)
            self.assertTrue(re.search(r"^description: .+", text, re.M), "%s 缺 description" % path)

    def test_stage_mapping_covers_all_seven_stages(self) -> None:
        mapping = (PA / "STAGE-MAPPING.md").read_text(encoding="utf-8")
        for stage in STAGES:
            self.assertIn("### " + stage, mapping)
        completed = support.run_script(CTL, ["list", "--json"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = json.loads(completed.stdout)["skills"]
        self.assertEqual(len(rows), 40)
        assigned = {row["stage"] for row in rows}
        self.assertTrue(set(STAGES).issubset(assigned))
        self.assertIn("router", assigned)

    def test_assetctl_stage_and_show(self) -> None:
        completed = support.run_script(CTL, ["stage", "release", "--json"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["stage"], "release")
        self.assertTrue(payload["count"] >= 8)
        names = {item["name"] for item in payload["skills"]}
        self.assertIn("p8-release-baseline-a", names)
        self.assertIn("p9-script-description", names)

        completed = support.run_script(CTL, ["show", "p8-release-baseline-a", "--json"])
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["skill"]["original_name"], "p8-release-baseline-A")

    def test_installer_is_dry_run_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            completed = support.run_script(INSTALL,
                ["dsh", "--scope", "project", "--project", temp, "--json"])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["count"], 40)
            self.assertTrue(payload["dry_run"])
            self.assertFalse((Path(temp) / ".dsh").exists(), "dry-run 不应写文件")

    def test_core_skills_unchanged_in_count(self) -> None:
        self.assertEqual(len(list((REPO / "skills").glob("*/SKILL.md"))), 10)


if __name__ == "__main__":
    unittest.main()
