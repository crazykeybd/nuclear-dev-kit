#!/usr/bin/env python3
"""发布包构建的确定性、内容与排除规则测试。"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

import support


class BuildDistTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.output = Path(self._temp.name) / "dist"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def build(self, output: Path) -> dict:
        completed = support.run_script(support.BUILD_DIST, ["--output", str(output), "--json"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return support.parse_json(completed.stdout)

    def test_archive_is_reproducible(self) -> None:
        first = self.build(self.output / "one")
        second = self.build(self.output / "two")
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual(first["files"], second["files"])

    def test_archive_layout_and_exclusions(self) -> None:
        payload = self.build(self.output)
        with zipfile.ZipFile(payload["archive"]) as bundle:
            names = bundle.namelist()
        self.assertIn("INSTALL.md", names)
        self.assertIn("SHA256SUMS.txt", names)
        self.assertIn("nuclear-dev-kit/README.md", names)
        self.assertIn("nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearlib.py", names)
        self.assertFalse(any(name.endswith(".pyc") for name in names))
        self.assertFalse(any("__pycache__" in name for name in names))
        self.assertFalse(any(name.endswith("方案.md") for name in names))
        self.assertFalse(any(name.endswith("工作记录.md") for name in names))
        self.assertFalse(any(name.endswith("CLAUDE.md") for name in names))
        self.assertEqual(names, sorted(names))

    def test_sha256sums_matches_archive_contents(self) -> None:
        payload = self.build(self.output)
        with zipfile.ZipFile(payload["archive"]) as bundle:
            sums = bundle.read("SHA256SUMS.txt").decode("utf-8").splitlines()
            listed = {}
            for line in sums:
                digest, name = line.split("  ", 1)
                listed[name] = digest
            for name, digest in listed.items():
                data = bundle.read(name)
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)
            self.assertNotIn("SHA256SUMS.txt", listed)
            self.assertEqual(sorted(listed), sorted(name for name in bundle.namelist() if name != "SHA256SUMS.txt"))

    def test_output_sums_file_matches_archive(self) -> None:
        payload = self.build(self.output)
        sums_file = Path(payload["sums"])
        self.assertTrue(sums_file.is_file())
        with zipfile.ZipFile(payload["archive"]) as bundle:
            self.assertEqual(sums_file.read_bytes(), bundle.read("SHA256SUMS.txt"))


if __name__ == "__main__":
    unittest.main()
