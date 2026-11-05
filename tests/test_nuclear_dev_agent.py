#!/usr/bin/env python3
"""nuclear-dev-agent 主体包与核能流程接入的回归测试。

覆盖三件事：
1. `tools/check_nuclear_dev_agent.py` 的 fork 完整性判定：包的身份、核能集成模块、
   旧身份回潮、`FORK.md` 的上游基点提交——干净树通过，四种坏树各自被点名；
2. `nuclear-dev-agent/` 作为本仓库主体包的自洽性（包名、许可证、构建产物不入库）；
3. 嵌入式用法真的成立：把 Skill 装进 Ticket worktree 的 `.dsh/skills` 后，
   门禁 CLI 能在该 worktree 上返回真实状态，且不改动项目源码。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

REPO = support.REPO
AGENT = REPO / "nuclear-dev-agent"
CHECK = REPO / "tools" / "check_nuclear_dev_agent.py"
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
NUCLEAR_FILES = [
    "src/nuclear/index.ts",
    "src/nuclear/scan.ts",
    "src/app/nuclear.ts",
    "src/app/views/nuclear.ts",
    "src/client/nuclear.tsx",
    "prompts/nuclear.md",
]


def load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_nuclear_dev_agent_module", str(CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_tree(base: Path, commit: str | None = None) -> Path:
    """造一棵最小的合法主体包：身份、核能模块、许可证、FORK.md 都在。"""
    module = load_module()
    commit = commit or module.EXPECTED_COMMIT
    files = {
        "package.json": json.dumps(
            {"name": "nuclear-dev-agent", "license": "MIT", "version": "0.0.0"}, indent=2
        ) + "\n",
        "cordis.patch.yml": (
            "- insert:\n"
            "    - id: nuclear-dev-agent\n"
            "      name: nuclear-dev-agent\n"
            "    - id: nuclear-dev-agent-github\n"
            "      name: nuclear-dev-agent/github-watch\n"
            "    - id: nuclear-dev-agent-feishu\n"
            "      name: nuclear-dev-agent/feishu-watch\n"
        ),
        "LICENSE": "MIT License\n\nCopyright (c) 2026\n",
        "FORK.md": "# 来源\n\n| 上游基点提交 | `%s`（main） |\n" % commit,
        "src/index.ts": "export const name = 'nuclear-dev-agent'\n",
        "src/nuclear/index.ts": "export const nuclear = true\n",
        "src/nuclear/scan.ts": "export const scan = true\n",
        "src/app/nuclear.ts": "export const snapshot = true\n",
        "src/app/views/nuclear.ts": "export const view = true\n",
        "src/client/nuclear.tsx": "export const panel = true\n",
        "prompts/nuclear.md": "七阶段门禁的硬约束。\n",
    }
    for relative, text in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return base


class AgentPackageTest(unittest.TestCase):
    """真仓库里的主体包：检查器通过，包身份与核能集成都在。"""

    def test_checker_passes(self) -> None:
        completed = support.run_script(CHECK, [])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("nuclear-dev-agent 主体包一致", completed.stdout)

    def test_checker_reports_commit_and_size(self) -> None:
        completed = support.run_script(CHECK, ["--json"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertRegex(payload["commit"], r"^[0-9a-f]{40}$")
        self.assertGreater(payload["files"], 100)
        self.assertEqual(payload["old_identity"]["count"], 0)
        self.assertEqual(payload["old_identity"]["paths"], [])

    def test_manifest_matches_dsh_contract(self) -> None:
        manifest = json.loads((AGENT / "package.json").read_text(encoding="utf-8"))
        # packageRoot() 按 name 找包根；改名字会让 prompts/skills 读不到。
        self.assertEqual(manifest["name"], "nuclear-dev-agent")
        self.assertEqual(manifest["license"], "MIT")
        self.assertIn("bundle", manifest["dsh"])
        self.assertIn("patch", manifest["dsh"]["bundle"])
        # 构建产物属于本机，不入库；本机已经构建过也不算错，只要 git 不会把它纳入版本库。
        ignore = (AGENT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("lib/", ignore)
        if (AGENT / "lib").exists():
            listed = subprocess.run(["git", "ls-files", "lib"], cwd=str(AGENT), capture_output=True, text=True)
            self.assertEqual(listed.stdout.strip(), "", "lib/ 是构建产物，不得入库")

    def test_license_is_preserved(self) -> None:
        text = (AGENT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("DeepSeek", text)

    def test_nuclear_integration_is_in_the_package(self) -> None:
        for relative in NUCLEAR_FILES:
            self.assertTrue((AGENT / relative).is_file(), "%s 是核能集成的一部分，不得缺失" % relative)

    def test_provenance_is_fork_md_not_vendor_md(self) -> None:
        self.assertTrue((AGENT / "FORK.md").is_file())
        self.assertFalse((AGENT / "VENDOR.md").exists(), "VENDOR.md 是旧只读副本的标记")

    def test_skills_stay_in_the_kit_root(self) -> None:
        """包内不得再放一份核能七阶段 Skill，避免两份规则漂移。"""
        found = sorted(
            path.parent.name
            for path in AGENT.rglob("SKILL.md")
            if "node_modules" not in path.parts
        )
        self.assertEqual(found, ["nuclear-dev-agent-feishu", "nuclear-dev-agent-github"])


class ForkIntegrityTest(unittest.TestCase):
    """坏树必须被点名：这是检查器存在的理由。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name) / "nuclear-dev-agent"
        make_tree(self.root)
        self.module = load_module()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_clean_tree_passes(self) -> None:
        completed = support.run_script(CHECK, ["--path", str(self.root)])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("主体包一致", completed.stdout)
        result = self.module.inspect(self.root)
        self.assertTrue(result["ok"], result["problems"])
        self.assertEqual(result["commit"], self.module.EXPECTED_COMMIT)
        self.assertGreater(result["files"], 0)

    def test_missing_nuclear_module_is_named(self) -> None:
        (self.root / "src" / "nuclear" / "index.ts").unlink()
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("src/nuclear/index.ts" in problem for problem in result["problems"]),
            result["problems"],
        )

    def test_reintroduced_old_identity_fails(self) -> None:
        legacy = self.root / "src" / "legacy.ts"
        legacy.write_text("export const name = 'dsh-superagent'\n", encoding="utf-8")
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["old_identity"]["count"], 1)
        self.assertEqual(result["old_identity"]["paths"], ["src/legacy.ts"])
        for token in self.module.OLD_IDENTITY:
            legacy.write_text("const token = '%s'\n" % token, encoding="utf-8")
            self.assertFalse(
                self.module.inspect(self.root)["ok"], "%s 回潮必须让检查失败" % token
            )

    def test_old_identity_scan_is_capped_and_counted(self) -> None:
        for index in range(12):
            (self.root / "src" / ("legacy%d.ts" % index)).write_text(
                "const legacy = 'DSH_SUPERAGENT_HOME'\n", encoding="utf-8"
            )
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["old_identity"]["count"], 12)
        self.assertEqual(len(result["old_identity"]["paths"]), self.module.MAX_LISTED)
        self.assertTrue(any("另有" in problem for problem in result["problems"]), result["problems"])

    def test_fork_commit_mismatch_fails(self) -> None:
        (self.root / "FORK.md").write_text(
            "| 上游基点提交 | `%s`（main） |\n" % ("0" * 40), encoding="utf-8"
        )
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["commit"], "0" * 40)
        self.assertTrue(
            any("EXPECTED_COMMIT" in problem for problem in result["problems"]), result["problems"]
        )

    def test_fork_without_commit_fails(self) -> None:
        (self.root / "FORK.md").write_text("# 来源\n\n未记录提交。\n", encoding="utf-8")
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["commit"])

    def test_vendor_marker_is_rejected(self) -> None:
        (self.root / "VENDOR.md").write_text("# 上游副本\n", encoding="utf-8")
        result = self.module.inspect(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("VENDOR.md" in problem for problem in result["problems"]))

    def test_missing_agent_dir_is_reported(self) -> None:
        result = self.module.inspect(Path(self._temp.name) / "nope")
        self.assertFalse(result["ok"])
        self.assertEqual(result["problems"], ["nuclear-dev-agent/ 目录不存在"])


class WorktreeEmbeddingTest(unittest.TestCase):
    """把核能 Skill 装进 nuclear-dev-agent 的 Ticket worktree，验证它真的可用。"""

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
