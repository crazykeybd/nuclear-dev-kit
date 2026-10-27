#!/usr/bin/env python3
"""安装器与便捷安装入口的回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support

SKILL_NAMES = [
    "nuclear-dev",
    "nuclear-setup",
    "nuclear-install",
    "nuclear-plan",
    "nuclear-requirements",
    "nuclear-design",
    "nuclear-implementation",
    "nuclear-test",
    "nuclear-vv",
    "nuclear-release",
]


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name)
        self.skills_root = self.project / ".claude" / "skills"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_dry_run_does_not_write(self) -> None:
        code, payload, err = support.run_install(
            self.project, "claude", "--scope", "project", "--json"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["status"], "planned")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(len(payload["targets"]), len(SKILL_NAMES))
        self.assertFalse(self.skills_root.exists())

    def test_install_writes_ten_skills(self) -> None:
        code, payload, err = support.run_install(
            self.project, "claude", "--scope", "project", "--yes", "--json"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["status"], "installed")
        for name in SKILL_NAMES:
            self.assertTrue((self.skills_root / name / "SKILL.md").is_file(), name)
        copied = list(self.skills_root.rglob("*"))
        self.assertFalse(any(path.name == "__pycache__" for path in copied))
        self.assertFalse(any(path.suffix == ".pyc" for path in copied))
        self.assertFalse((self.project / "README.md").exists())

    def test_second_install_conflicts_without_force(self) -> None:
        support.run_install(self.project, "claude", "--scope", "project", "--yes", "--json")
        code, payload, _ = support.run_install(self.project, "claude", "--scope", "project", "--yes", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "conflict")
        self.assertEqual(len(payload["conflicts"]), len(SKILL_NAMES))

    def test_force_creates_backup_before_overwrite(self) -> None:
        support.run_install(self.project, "claude", "--scope", "project", "--yes", "--json")
        code, payload, err = support.run_install(
            self.project, "claude", "--scope", "project", "--yes", "--force", "--json"
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(payload["backups"])
        for backup in payload["backups"]:
            self.assertTrue(Path(backup).exists(), backup)
        self.assertIn(".nuclear-dev-kit-backups", payload["backups"][0])

    def test_all_hosts_deduplicates_shared_paths(self) -> None:
        code, payload, err = support.run_install(
            self.project, "all", "--scope", "project", "--json"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(payload["hosts"]), ["claude", "codex", "opencode", "reasonix"])
        self.assertEqual(len(payload["targets"]), len(SKILL_NAMES) * len(payload["hosts"]))

    def test_one_failing_host_does_not_block_the_others(self) -> None:
        # codex 的项目级根目录是 .agents/skills；把 .agents 做成文件让它必然失败
        (self.project / ".agents").write_text("not a directory", encoding="utf-8")
        code, payload, _ = support.run_install(
            self.project, "all", "--scope", "project", "--yes", "--json"
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "partial")
        self.assertIn("codex", [item["host"] for item in payload["failures"]])
        for root in (".claude", ".opencode", ".reasonix"):
            self.assertTrue(
                (self.project / root / "skills" / "nuclear-dev" / "SKILL.md").is_file(), root
            )
        self.assertTrue((self.project / ".agents").is_file())

    def test_project_scope_requires_project_argument(self) -> None:
        completed = support.run_script(
            support.INSTALL, ["claude", "--scope", "project", "--json"]
        )
        self.assertEqual(completed.returncode, 2)
        payload = support.parse_json(completed.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("project", payload["error"])

    def test_reasonix_project_uses_dot_reasonix(self) -> None:
        code, payload, err = support.run_install(
            self.project, "reasonix", "--scope", "project", "--json"
        )
        self.assertEqual(code, 0, err)
        root = self.project / ".reasonix" / "skills"
        for target in payload["targets"]:
            self.assertEqual(Path(target["destination"]).parent, root)

    def test_reasonix_global_honors_reasonix_home(self) -> None:
        with tempfile.TemporaryDirectory() as reasonix_home:
            env = support.child_env()
            env["REASONIX_HOME"] = reasonix_home
            completed = support.run_script(
                support.INSTALL, ["reasonix", "--scope", "global", "--json"], env=env
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = support.parse_json(completed.stdout)
            root = Path(reasonix_home).resolve() / "skills"
            for target in payload["targets"]:
                self.assertEqual(Path(target["destination"]).parent, root)


class QuickInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_dry_run_plan_is_reported_without_writing(self) -> None:
        completed = support.run_script(
            support.QUICKINSTALL,
            ["claude", "--scope", "project", "--project", str(self.project), "--json"],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = support.parse_json(completed.stdout)
        self.assertEqual(payload["status"], "planned")
        self.assertEqual(payload["host"], "claude")
        self.assertFalse((self.project / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
