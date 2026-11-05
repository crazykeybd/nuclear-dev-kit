#!/usr/bin/env python3
"""`tools/deploy_nuclear_dev_agent.py` 的回归测试：一条命令部署的编排与幂等性。

纯函数部分（bundles/patch/技能探测）在所有平台跑；需要伪造可执行文件的端到端
编排只在 POSIX 上跑（Windows 上 shell 脚本不可直接执行，与既有权限用例同样处理）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

REPO = support.REPO
DEPLOY = REPO / "tools" / "deploy_nuclear_dev_agent.py"
SKILLS = [
    "nuclear-dev", "nuclear-setup", "nuclear-install", "nuclear-plan", "nuclear-requirements",
    "nuclear-design", "nuclear-implementation", "nuclear-test", "nuclear-vv", "nuclear-release",
]

FAKE_DSH = """#!/bin/sh
case "$1" in
  plugin) exit 0 ;;
  --profile)
    case "$3" in
      --dump-config) printf -- '- id: nuclear-dev-agent\\n- id: mcp-nuclear-dev\\n- id: skill-filesystem\\n'; exit 0 ;;
    esac
    exit 0 ;;
  *)
    mkdir -p "$DSH_HOME/profiles/$1"
    printf '{"name": "dsh-profile-%s", "private": true}\\n' "$1" > "$DSH_HOME/profiles/$1/package.json"
    exit 0 ;;
esac
"""

FAKE_PNPM = """#!/bin/sh
if [ "$1" = "install" ]; then mkdir -p node_modules; exit 0; fi
if [ "$1" = "build" ]; then mkdir -p lib && echo "export {}" > lib/index.js; exit 0; fi
exit 0
"""


def make_agent(base: Path, built: bool = False) -> Path:
    """造一个最小 agent 包目录：只有 package.json（和可选的 lib/）。"""
    base.mkdir(parents=True, exist_ok=True)
    (base / "package.json").write_text(
        json.dumps({"name": "nuclear-dev-agent", "version": "0.0.0"}) + "\n", encoding="utf-8"
    )
    if built:
        (base / "lib").mkdir()
        (base / "lib" / "index.js").write_text("export {}\n", encoding="utf-8")
    return base


def load_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("deploy_nuclear-dev-agent_module", str(DEPLOY))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PlanTest(unittest.TestCase):
    def test_dry_run_plans_every_step_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent")
            completed = support.run_script(
                DEPLOY, ["--json", "--dsh-home", str(home), "--agent-dir", str(agent)],
                env=support.child_env(),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"], payload)
            self.assertTrue(payload["dry_run"])
            steps = [step["step"] for step in payload["steps"]]
            for name in ("build", "skills", "profile", "bundles", "patch"):
                self.assertIn(name, steps)
            self.assertEqual(steps.count("link"), 2)
            # dry-run 不得落任何文件
            self.assertEqual([p for p in Path(home).rglob("*")], [])

    def test_dry_run_previews_the_patch_it_would_append(self) -> None:
        """预览里就要看到写进去的内容：kitPath 指向本仓库根，python 是当前解释器。"""
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent")
            completed = support.run_script(
                DEPLOY, ["--json", "--dsh-home", str(home), "--agent-dir", str(agent)],
                env=support.child_env(),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            patch = [step for step in payload["steps"] if step["step"] == "patch"][0]
            self.assertIn("nuclear-dev-agent", patch["missing"])
            preview = patch["preview"]
            self.assertIn("kitPath: %s" % REPO, preview)
            self.assertIn("python: %s" % sys.executable, preview)
            self.assertIn("stateDir: %s" % (Path(home).resolve() / "state" / "nuclear-dev-agent"), preview)

    def test_plan_uses_user_skill_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent")
            completed = support.run_script(
                DEPLOY, ["--json", "--dsh-home", str(home), "--agent-dir", str(agent)],
                env=support.child_env(),
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["skills_root"], str(Path(home).resolve() / "skills"))
            self.assertEqual(payload["profile_dir"], str(Path(home).resolve() / "profiles" / "nuclear-dev-agent"))

    def test_dry_run_survives_missing_pnpm_and_reports_it(self) -> None:
        """预览阶段不该因为机器上没有 pnpm 就失败：先告诉人缺什么。"""
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent")
            completed = support.run_script(
                DEPLOY,
                [
                    "--json", "--dsh-home", str(home), "--agent-dir", str(agent),
                    "--pnpm-bin", str(Path(temp) / "no-such-pnpm"),
                ],
                env=support.child_env(),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"], payload)
            build = [step for step in payload["steps"] if step["step"] == "build"][0]
            self.assertTrue(build["needed"])
            self.assertEqual(build["missing_tools"], [str(Path(temp) / "no-such-pnpm")])

    def test_execute_fails_when_pnpm_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent")
            completed = support.run_script(
                DEPLOY,
                [
                    "--json", "--yes", "--dsh-home", str(home), "--agent-dir", str(agent),
                    "--pnpm-bin", str(Path(temp) / "no-such-pnpm"),
                ],
                env=support.child_env(),
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("pnpm", payload["error"])

    def test_plan_rejects_skip_build_without_lib(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "home"
            agent = make_agent(Path(temp) / "agent", built=False)
            completed = support.run_script(
                DEPLOY,
                ["--json", "--dsh-home", str(home), "--agent-dir", str(agent), "--skip-build", "--yes"],
                env=support.child_env(),
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("lib", payload["error"])


class BundlesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.path = Path(self._temp.name) / "profiles" / "nuclear-dev-agent" / "package.json"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_merge_keeps_existing_entries(self) -> None:
        module = load_module()
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"name": "dsh-profile-nuclear-dev-agent", "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base"]}}}) + "\n",
            encoding="utf-8",
        )
        result = module.merge_bundles(self.path, dry_run=False)
        self.assertEqual(result["missing"], ["@deepseek-ai/dsh-web-app", "nuclear-dev-agent", "nuclear-dev-kit"])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "dsh-profile-nuclear-dev-agent")
        self.assertEqual(
            data["dsh"]["profile"]["bundles"],
            ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "nuclear-dev-agent", "nuclear-dev-kit"],
        )
        self.assertTrue(result["backup"] and Path(result["backup"]).is_file())

    def test_merge_is_idempotent(self) -> None:
        module = load_module()
        module.merge_bundles(self.path, dry_run=False)
        first = self.path.read_text(encoding="utf-8")
        second_plan = module.merge_bundles(self.path, dry_run=False)
        self.assertEqual(second_plan["missing"], [])
        self.assertEqual(self.path.read_text(encoding="utf-8"), first)

    def test_dry_run_does_not_write(self) -> None:
        module = load_module()
        result = module.merge_bundles(self.path, dry_run=True)
        self.assertTrue(result["missing"])
        self.assertFalse(self.path.exists())


class PatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.profile = Path(self._temp.name) / "profiles" / "nuclear-dev-agent"
        self.profile.mkdir(parents=True)
        self.state = Path(self._temp.name) / "state" / "nuclear-dev-agent"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_writes_rows_with_absolute_paths(self) -> None:
        module = load_module()
        result = module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        self.assertEqual(len(result["missing"]), 3)
        text = (self.profile / "cordis.patch.yml").read_text(encoding="utf-8")
        self.assertIn("port: 3082", text)
        self.assertIn("stateDir: %s" % self.state, text)
        self.assertIn("serverName: nuclear-dev", text)
        self.assertIn(str(module.SERVER), text)
        self.assertNotIn("process.env", text)

    def test_agent_block_points_the_agent_at_the_kit(self) -> None:
        """agent 包自己跑 kit 的命令行：kitPath 必须是本仓库根，python 必须是给出的解释器。"""
        module = load_module()
        module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        text = (self.profile / "cordis.patch.yml").read_text(encoding="utf-8")
        self.assertIn("- id: nuclear-dev-agent\n  config:\n    stateDir: ", text)
        self.assertIn("\n    nuclear:\n", text)
        self.assertIn("      kitPath: %s\n" % module.REPO, text)
        self.assertIn("      python: /usr/bin/python3\n", text)

    def test_dry_run_reports_the_block_without_writing(self) -> None:
        module = load_module()
        result = module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=True)
        self.assertIn("nuclear-dev-agent", result["missing"])
        self.assertIn("kitPath: %s" % module.REPO, result["preview"])
        self.assertIn("python: /usr/bin/python3", result["preview"])
        self.assertFalse((self.profile / "cordis.patch.yml").exists())

    def test_second_write_keeps_file_unchanged(self) -> None:
        module = load_module()
        module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        first = (self.profile / "cordis.patch.yml").read_text(encoding="utf-8")
        again = module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        self.assertEqual(again["missing"], [])
        self.assertEqual((self.profile / "cordis.patch.yml").read_text(encoding="utf-8"), first)

    def test_appends_to_foreign_patch_and_keeps_it(self) -> None:
        """profile 已有别人写的配置时，只追加缺的块，不覆盖也不丢原有内容。"""
        module = load_module()
        target = self.profile / "cordis.patch.yml"
        original = "# 别人的配置\n- id: webserver\n  config:\n    port: 9\n"
        target.write_text(original, encoding="utf-8")
        result = module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        self.assertEqual(result["kept"], ["webserver"])
        self.assertEqual(result["missing"], ["nuclear-dev-agent", "mcp-nuclear-dev"])
        text = target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original), text)
        self.assertIn("stateDir: %s" % self.state, text)
        self.assertIn("kitPath: %s" % module.REPO, text)
        self.assertIn("serverName: nuclear-dev", text)
        # 原配置里的端口不被改写
        self.assertNotIn("port: 3082", text)
        self.assertTrue(result["backup"] and Path(result["backup"]).is_file())

    def test_existing_all_ids_leaves_file_untouched(self) -> None:
        module = load_module()
        target = self.profile / "cordis.patch.yml"
        target.write_text(
            "- id: webserver\n- id: nuclear-dev-agent\n- id: mcp-nuclear-dev\n", encoding="utf-8"
        )
        result = module.patch_rows(self.profile, 3082, self.state, "/usr/bin/python3", dry_run=False)
        self.assertEqual(result["missing"], [])
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            "- id: webserver\n- id: nuclear-dev-agent\n- id: mcp-nuclear-dev\n",
        )


class SkillProbeTest(unittest.TestCase):
    def test_present_skills_detects_nothing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(module.present_skills(Path(root)), [])

    def test_present_skills_needs_skill_md(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            for name in SKILLS:
                (base / name).mkdir(parents=True, exist_ok=True)
            (base / "nuclear-plan" / "SKILL.md").write_text("---\nname: nuclear-plan\n---\n", encoding="utf-8")
            self.assertEqual(module.present_skills(base), ["nuclear-plan"])

    def test_plan_skills_skips_when_all_present(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as root:
            for name in SKILLS:
                (Path(root) / name).mkdir(parents=True)
                (Path(root) / name / "SKILL.md").write_text("x", encoding="utf-8")
            step = module.plan_skills(Path(root), refresh=False)
            self.assertFalse(step["needed"])
            self.assertNotIn("command", step)

    def test_plan_skills_uses_force_for_partial_install(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "nuclear-dev").mkdir(parents=True)
            (Path(root) / "nuclear-dev" / "SKILL.md").write_text("x", encoding="utf-8")
            step = module.plan_skills(Path(root), refresh=False)
            self.assertTrue(step["needed"])
            self.assertIn("--force", step["command"])


@unittest.skipIf(os.name == "nt", "伪造的可执行脚本依赖 POSIX shell")
class EndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        base = Path(self._temp.name)
        self.home = base / "dshhome"
        self.bin = base / "bin"
        self.bin.mkdir()
        for name, body in (("dsh", FAKE_DSH), ("pnpm", FAKE_PNPM)):
            path = self.bin / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        # 临时 agent 包：构建产物落在临时目录，绝不污染仓库里的 nuclear-dev-agent/
        self.agent = make_agent(base / "agent")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def deploy(self, *argv: str):
        env = support.child_env()
        env["DSH_HOME"] = str(self.home)
        completed = support.run_script(
            DEPLOY,
            [
                "--json", "--yes",
                "--dsh-bin", str(self.bin / "dsh"),
                "--pnpm-bin", str(self.bin / "pnpm"),
                "--agent-dir", str(self.agent),
            ]
            + list(argv),
            env=env,
        )
        return completed

    def test_one_command_deploys_everything(self) -> None:
        completed = self.deploy()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        # 伪造的 pnpm 在临时 agent 包里产出 lib/，证明构建步骤真的被执行
        self.assertTrue((self.agent / "lib" / "index.js").is_file())

        # 1) 十个 Skill 进用户级 Skill 根：所有 Session 都能看到，不需要 prepare 命令
        installed = sorted(p.parent.name for p in (self.home / "skills").glob("*/SKILL.md"))
        self.assertEqual(installed, sorted(SKILLS))

        # 2) profile 的三个 bundle 都登记了
        manifest = json.loads((self.home / "profiles" / "nuclear-dev-agent" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["dsh"]["profile"]["bundles"],
            ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "nuclear-dev-agent", "nuclear-dev-kit"],
        )

        # 3) 机器配置里是绝对路径，不依赖环境变量
        patch = (self.home / "profiles" / "nuclear-dev-agent" / "cordis.patch.yml").read_text(encoding="utf-8")
        self.assertIn("mcp-nuclear-dev", patch)
        self.assertIn(str(REPO / "skills" / "nuclear-dev" / "scripts" / "nuclearmcp.py"), patch)
        self.assertNotIn("process.env", patch)

        # 4) agent 包拿到 kit 路径与解释器，才能自己跑门禁命令行
        self.assertIn("      kitPath: %s\n" % REPO, patch)
        self.assertRegex(patch, r"(?m)^      python: \S+$")
        self.assertIn("      python: %s\n" % sys.executable, patch)

    def test_second_run_is_idempotent(self) -> None:
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        patch_before = (self.home / "profiles" / "nuclear-dev-agent" / "cordis.patch.yml").read_text(encoding="utf-8")

        second = self.deploy("--skip-build")
        self.assertEqual(second.returncode, 0, second.stderr)
        payload = json.loads(second.stdout)
        skills = [step for step in payload["steps"] if step["step"] == "skills"]
        self.assertFalse(any(step.get("needed") for step in skills), skills)
        self.assertEqual(
            (self.home / "profiles" / "nuclear-dev-agent" / "cordis.patch.yml").read_text(encoding="utf-8"),
            patch_before,
        )


if __name__ == "__main__":
    unittest.main()
