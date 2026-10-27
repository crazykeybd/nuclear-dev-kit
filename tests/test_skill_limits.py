#!/usr/bin/env python3
"""Skill 文件的宿主能力上限与文档一致性测试。

Codex 对 Skill 正文有 8 KB 硬上限，超限会被截断且不报错。
本测试把该限制变成回归失败，避免"看起来写完了、宿主实际只读到一半"。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import support

REPO = support.REPO
SKILLS_ROOT = REPO / "skills"
MAX_SKILL_BYTES = 8192

HOST_DOCS = [
    SKILLS_ROOT / "nuclear-dev" / "references" / "host-compatibility.md",
    SKILLS_ROOT / "nuclear-setup" / "references" / "host-compatibility.md",
]

SIZE_ROW = re.compile(r"^\|\s*(nuclear-[a-z]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION_CHARS = 1024


def frontmatter_of(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    block = text.split("---", 2)[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            if value.strip():
                fields[key.strip()] = value.strip().strip('"')
    return fields


def skill_files() -> list[Path]:
    return sorted(SKILLS_ROOT.glob("*/SKILL.md"))


def documented_sizes(path: Path) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SIZE_ROW.match(line.strip())
        if match:
            sizes[match.group(1)] = int(match.group(2))
    return sizes


class SkillLimitsTest(unittest.TestCase):
    def test_every_skill_has_frontmatter(self) -> None:
        files = skill_files()
        self.assertEqual(len(files), 10, "应恰好有 10 个 Skill")
        for path in files:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), "%s 缺少 frontmatter" % path)
            self.assertIn("\nname: ", text.split("---", 2)[1], "%s 缺少 name" % path)

    def test_skill_names_follow_agent_skills_rules(self) -> None:
        """Reasonix、opencode 等 Agent Skills 宿主要求 name 为小写短横线格式。"""
        for path in skill_files():
            fields = frontmatter_of(path)
            name = fields.get("name", "")
            self.assertRegex(name, SKILL_NAME, "%s 的 name 不符合 Agent Skills 规则" % path)
            self.assertEqual(
                name,
                path.parent.name,
                "%s 的 name 必须与所在目录同名" % path,
            )

    def test_descriptions_within_agent_skills_limit(self) -> None:
        for path in skill_files():
            description = frontmatter_of(path).get("description", "")
            self.assertTrue(description, "%s 缺少 description" % path)
            self.assertLessEqual(
                len(description),
                MAX_DESCRIPTION_CHARS,
                "%s 的 description 超过 %d 字符" % (path, MAX_DESCRIPTION_CHARS),
            )

    def test_every_skill_under_codex_body_cap(self) -> None:
        for path in skill_files():
            size = len(path.read_bytes())
            self.assertLessEqual(
                size,
                MAX_SKILL_BYTES,
                "%s 为 %d 字节，超过 Codex 的 %d 字节上限" % (path, size, MAX_SKILL_BYTES),
            )

    def test_skills_use_lf_and_utf8(self) -> None:
        for path in skill_files():
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw, "%s 含 CRLF 换行" % path)
            raw.decode("utf-8")

    def test_documented_sizes_match_actual(self) -> None:
        actual = {path.parent.name: len(path.read_bytes()) for path in skill_files()}
        for doc in HOST_DOCS:
            documented = documented_sizes(doc)
            self.assertTrue(documented, "%s 未找到字节数表格" % doc)
            self.assertEqual(
                documented,
                actual,
                "%s 中记录的 SKILL.md 字节数与实际不一致，请同步更新" % doc,
            )
            for name, size in documented.items():
                self.assertLessEqual(size, MAX_SKILL_BYTES, "%s 的记录已超上限" % name)


if __name__ == "__main__":
    unittest.main()
