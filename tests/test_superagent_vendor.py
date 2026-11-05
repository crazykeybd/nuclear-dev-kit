#!/usr/bin/env python3
"""superagent 副本与核能流程接入的回归测试。

覆盖三件事：
1. `superagent/` 是上游 dsh-superagent 的完整源码副本，来源可追溯，本机产物不入库；
2. 上游目录保持零改动——核能 Skill 的**唯一**事实来源仍是仓库根的 `skills/`；
3. 嵌入式用法真的成立：把 Skill 装进 Ticket worktree 的 `.dsh/skills` 后，
   门禁 CLI 能在该 worktree 上返回真实状态，且不改动项目源码。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import support

REPO = support.REPO
VENDOR = REPO / "superagent"
CHECK = REPO / "tools" / "check_superagent_vendor.py"
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


class VendorIntegrityTest(unittest.TestCase):
    def test_checker_passes(self) -> None:
        completed = support.run_script(CHECK, [])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("superagent 副本一致", completed.stdout)

    def test_checker_reports_commit_and_size(self) -> None:
        completed = support.run_script(CHECK, ["--json"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertRegex(payload["commit"], r"^[0-9a-f]{40}$")
        self.assertGreater(payload["files"], 150)

    def test_upstream_manifest_matches_dsh_contract(self) -> None:
        manifest = json.loads((VENDOR / "package.json").read_text(encoding="utf-8"))
        # packageRoot() 按 name 找包根；改名字会让 prompts/skills 读不到。
        self.assertEqual(manifest["name"], "dsh-superagent")
        self.assertEqual(manifest["license"], "MIT")
        self.assertIn("bundle", manifest["dsh"])
        self.assertIn("patch", manifest["dsh"]["bundle"])
        # 上游把构建产物排除在版本库外，本仓库沿用同一约定。
        ignore = (VENDOR / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("lib/", ignore)
        self.assertFalse((VENDOR / "lib").exists(), "lib/ 是构建产物，不得入库")

    def test_license_is_preserved(self) -> None:
        text = (VENDOR / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("DeepSeek", text)

    def test_skills_stay_in_the_kit_root(self) -> None:
        """上游目录里不得再放一份 nuclear Skill，避免两份规则漂移。"""
        for path in VENDOR.rglob("SKILL.md"):
            self.assertFalse(
                path.parent.name.startswith("nuclear-"),
                "%s 是第二份核能 Skill，会与 skills/ 漂移" % path,
            )
        upstream = sorted(p.parent.name for p in VENDOR.glob("skills/*/SKILL.md"))
        self.assertEqual(upstream, ["dsh-superagent-feishu", "dsh-superagent-github"])


class WorktreeEmbeddingTest(unittest.TestCase):
    """把核能 Skill 装进 superagent 的 Ticket worktree，验证它真的可用。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.repo = Path(self._temp.name) / "nuclear-proj"
        self.repo.mkdir()
        git = ["git", "-C", str(self.repo)]
        for argv in (
            ["init", "-q"],
            ["-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q",
             "--allow-empty", "-m", "init"],
        ):
            completed = subprocess.run(git + argv, capture_output=True, text=True)
            if completed.returncode != 0:
                self.skipTest("本机没有可用的 git，跳过 worktree 用例：%s" % completed.stderr.strip())
        self.worktree = Path(self._temp.name) / "ticket-worktree"
        completed = subprocess.run(
            git + ["worktree", "add", "-q", "-b", "agent/ticket", str(self.worktree), "HEAD"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def install(self, *argv: str):
        return support.run_install(self.worktree, "dsh", "--scope", "project", "--json", *argv)

    def test_worktree_dot_git_is_a_file(self) -> None:
        """dsh-skill-filesystem 以 .git 是否存在找项目根，worktree 的 .git 是文件。"""
        self.assertTrue((self.worktree / ".git").is_file())

    def test_dry_run_writes_nothing(self) -> None:
        code, payload, err = self.install()
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["status"], "planned")
        self.assertEqual(len(payload["targets"]), len(SKILL_NAMES))
        self.assertFalse((self.worktree / ".dsh").exists())

    def test_install_puts_ten_skills_in_the_worktree(self) -> None:
        code, payload, err = self.install("--yes")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["status"], "installed")
        root = self.worktree / ".dsh" / "skills"
        installed = sorted(p.parent.name for p in root.glob("*/SKILL.md"))
        self.assertEqual(installed, sorted(SKILL_NAMES))

    def test_installed_copy_is_self_contained(self) -> None:
        self.install("--yes")
        copied = self.worktree / ".dsh" / "skills" / "nuclear-dev" / "scripts" / "nuclearlib.py"
        self.assertTrue(copied.is_file(), "安装器必须连 scripts/ 一起复制，否则 worktree 里跑不了门禁")

    def test_reinstall_conflicts_without_force(self) -> None:
        self.install("--yes")
        code, payload, _ = self.install("--yes")
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "conflict")
        self.assertEqual(len(payload["conflicts"]), len(SKILL_NAMES))

    def test_gate_runs_on_the_installed_worktree(self) -> None:
        self.install("--yes")
        control = self.worktree / ".dsh" / "skills" / "nuclear-dev" / "scripts" / "nuclearctl.py"
        completed = support.run_script(
            control, ["--root", str(self.worktree), "init", "--name", "示例", "--id", "example", "--json"]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])
        status = support.run_script(control, ["--root", str(self.worktree), "status", "--json"])
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(len(json.loads(status.stdout)["stages"]), 7)

    def test_install_does_not_touch_project_source(self) -> None:
        before = subprocess.run(
            ["git", "-C", str(self.worktree), "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout
        self.assertEqual(before.strip(), "")
        self.install("--yes")
        after = subprocess.run(
            ["git", "-C", str(self.worktree), "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout
        # 只多出 .dsh/ 这一处未跟踪目录，源码文件一字未动。
        self.assertEqual([line[3:] for line in after.splitlines()], [".dsh/"])


if __name__ == "__main__":
    unittest.main()
