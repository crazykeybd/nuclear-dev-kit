#!/usr/bin/env python3
"""Reasonix 部署状态检查器的回归测试。

覆盖 tools/check_reasonix_deploy.py 的五种状态；全部在临时目录内进行，
不会读取或修改本机真实的 Reasonix 配置。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import support

CHECKER = support.REPO / "tools" / "check_reasonix_deploy.py"
SKILLS_ROOT = support.REPO / "skills"


def copy_skills(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source in sorted(SKILLS_ROOT.iterdir()):
        if source.is_dir():
            shutil.copytree(source, target / source.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def write_plugin(home: Path, name: str = "nuclear-dev") -> None:
    config = home / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.is_file() else ""
    block = '[[plugins]]\nname = "%s"\ntype = "stdio"\ncommand = "python"\nargs = ["server.py"]\n' % name
    config.write_text(existing + "\n" + block, encoding="utf-8")


class ReasonixDeployCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_check(self) -> tuple[int, dict]:
        completed = support.run_script(CHECKER, ["--home", str(self.home), "--json"])
        return completed.returncode, json.loads(completed.stdout)

    def test_not_deployed(self) -> None:
        code, payload = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "not_deployed")
        self.assertEqual(payload["missing_skills"], payload["expected_skills"])

    def test_up_to_date(self) -> None:
        copy_skills(self.home / "skills")
        write_plugin(self.home)
        code, payload = self.run_check()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "up_to_date")
        self.assertTrue(payload["plugin_registered"])

    def test_partial(self) -> None:
        copy_skills(self.home / "skills")
        shutil.rmtree(self.home / "skills" / "nuclear-vv")
        write_plugin(self.home)
        code, payload = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["missing_skills"], ["nuclear-vv"])

    def test_needs_update(self) -> None:
        copy_skills(self.home / "skills")
        write_plugin(self.home)
        target = self.home / "skills" / "nuclear-plan" / "SKILL.md"
        target.write_text(target.read_text(encoding="utf-8") + "\n已过期的本地改动\n", encoding="utf-8")
        code, payload = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "needs_update")
        self.assertIn("nuclear-plan", payload["changed_skills"])

    def test_config_missing(self) -> None:
        copy_skills(self.home / "skills")
        code, payload = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "config_missing")
        self.assertFalse(payload["plugin_registered"])

    def test_other_plugin_does_not_count(self) -> None:
        copy_skills(self.home / "skills")
        write_plugin(self.home, name="some-other-server")
        code, payload = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "config_missing")

    def test_backup_directory_is_not_counted_as_skill(self) -> None:
        copy_skills(self.home / "skills")
        write_plugin(self.home)
        backup = self.home / "skills" / ".nuclear-dev-kit-backups" / "20260101T000000Z" / "nuclear-dev"
        shutil.copytree(self.home / "skills" / "nuclear-dev", backup)
        code, payload = self.run_check()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["status"], "up_to_date")
        self.assertEqual(payload["extra_skills"], [])


if __name__ == "__main__":
    unittest.main()
