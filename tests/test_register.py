#!/usr/bin/env python3
"""MCP 注册片段生成的回归测试。"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import support


def run_register(*argv: str):
    completed = support.run_script(support.REGISTER, [str(item) for item in argv] + ["--json"])
    return completed, support.parse_json(completed.stdout)


class ClaudeSnippetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_default_is_read_only_and_does_not_write(self) -> None:
        completed, payload = run_register("claude", "--scope", "project", "--project", str(self.project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["wrote"])
        self.assertFalse((self.project / ".mcp.json").exists())
        server = payload["snippet"]["mcpServers"]["nuclear-dev"]
        self.assertEqual(server["command"], payload["python"])
        self.assertIn("--workspace", server["args"])
        self.assertNotIn("--allow-write", server["args"])
        self.assertTrue(server["args"][0].endswith("nuclearmcp.py"))

    def test_allow_write_adds_flag(self) -> None:
        completed, payload = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--allow-write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        server = payload["snippet"]["mcpServers"]["nuclear-dev"]
        self.assertIn("--allow-write", server["args"])

    def test_installed_copy_is_preferred(self) -> None:
        code, _, err = support.run_install(
            self.project, "claude", "--scope", "project", "--yes", "--json"
        )
        self.assertEqual(code, 0, err)
        completed, payload = run_register("claude", "--scope", "project", "--project", str(self.project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["server_source"], "installed")
        self.assertIn(".claude", payload["server_path"])
        self.assertTrue(Path(payload["server_path"]).is_file())

    def test_write_merges_and_keeps_existing_servers(self) -> None:
        config = self.project / ".mcp.json"
        original = json.dumps({"mcpServers": {"other": {"command": "other-bin", "args": []}}}, indent=2) + "\n"
        config.write_text(original, encoding="utf-8")
        completed, payload = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["wrote"])
        data = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(set(data["mcpServers"]), {"other", "nuclear-dev"})
        self.assertEqual(data["mcpServers"]["other"]["command"], "other-bin")
        self.assertTrue(payload["backup"])
        self.assertEqual(Path(payload["backup"]).read_text(encoding="utf-8"), original)

    def test_second_write_creates_backup(self) -> None:
        run_register("claude", "--scope", "project", "--project", str(self.project), "--write")
        completed, payload = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["backup"])
        self.assertTrue(Path(payload["backup"]).is_file())

    def test_invalid_existing_config_is_not_overwritten(self) -> None:
        config = self.project / ".mcp.json"
        config.write_text("{not json", encoding="utf-8")
        completed, payload = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(config.read_text(encoding="utf-8"), "{not json")

    def test_write_leaves_no_temporary_file(self) -> None:
        completed, _ = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        leftovers = [path.name for path in self.project.iterdir() if path.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_project_scope_requires_project(self) -> None:
        completed, payload = run_register("claude", "--scope", "project")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--project", payload["error"])

    def test_missing_workspace_is_rejected(self) -> None:
        completed, payload = run_register(
            "claude",
            "--scope",
            "project",
            "--project",
            str(self.project),
            "--workspace",
            str(self.project / "missing"),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("workspace", payload["error"])

    def test_registered_command_starts_a_real_server(self) -> None:
        code, _, err = support.run_install(
            self.project, "claude", "--scope", "project", "--yes", "--json"
        )
        self.assertEqual(code, 0, err)
        completed, payload = run_register(
            "claude", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        config = json.loads((self.project / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["nuclear-dev"]
        process = subprocess.Popen(
            [server["command"]] + server["args"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=support.child_env(),
        )
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            }
            process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
            process.stdin.flush()
            response = json.loads(process.stdout.readline().decode("utf-8"))
        finally:
            process.terminate()
            process.wait(timeout=10)
        self.assertEqual(response["result"]["serverInfo"]["name"], "nuclear-dev-bot")


class OtherHostSnippetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_codex_emits_toml_without_writing(self) -> None:
        completed, payload = run_register("codex", "--scope", "project", "--project", str(self.project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["format"], "toml")
        self.assertIn("[mcp_servers.nuclear-dev]", payload["snippet"])
        self.assertIn("command = ", payload["snippet"])
        self.assertFalse(any(self.project.iterdir()))

    def test_reasonix_project_emits_mcp_json(self) -> None:
        completed, payload = run_register(
            "reasonix", "--scope", "project", "--project", str(self.project)
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["format"], "json")
        self.assertIn("mcpServers", payload["snippet"])
        self.assertFalse((self.project / ".mcp.json").exists())
        self.assertIn(".mcp.json", payload["config_path"])

    def test_reasonix_project_writes_mcp_json(self) -> None:
        completed, payload = run_register(
            "reasonix", "--scope", "project", "--project", str(self.project), "--write"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["wrote"])
        data = json.loads((self.project / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("nuclear-dev", data["mcpServers"])

    def test_reasonix_global_emits_plugins_toml(self) -> None:
        completed, payload = run_register("reasonix", "--scope", "global")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["format"], "toml")
        self.assertIn("[[plugins]]", payload["snippet"])
        self.assertIn('name = "nuclear-dev"', payload["snippet"])
        self.assertIn("args = [", payload["snippet"])
        self.assertIn("config.toml", payload["config_path"])

    def test_generic_emits_neutral_spec(self) -> None:
        completed, payload = run_register("generic", "--scope", "project", "--project", str(self.project))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["snippet"]["name"], "nuclear-dev")
        self.assertEqual(payload["snippet"]["transport"], "stdio")

    def test_global_scope_uses_isolated_home(self) -> None:
        """全局范围不得解析到开发者的真实用户目录。"""
        completed, payload = run_register("reasonix", "--scope", "global")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        config = Path(payload["config_path"]).resolve()
        self.assertTrue(config.is_relative_to(support.isolated_home().resolve()), config)


class ReasonixConfigWriteTest(unittest.TestCase):
    """Reasonix 全局 config.toml 的 [[plugins]] 自动追加。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.home = Path(self._temp.name)
        self.config = self.home / "config.toml"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def run_with_home(self, *argv: str):
        env = support.child_env()
        env["REASONIX_HOME"] = str(self.home)
        completed = support.run_script(
            support.REGISTER, [str(item) for item in argv] + ["--json"], env=env
        )
        return completed, support.parse_json(completed.stdout)

    def write_config(self, text: str) -> None:
        with self.config.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def test_write_appends_plugins_and_backs_up(self) -> None:
        original = 'config_version = 12\ndefault_model = "localhost/cn:hy3"\n'
        self.write_config(original)
        completed, payload = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["wrote"])
        self.assertTrue(Path(payload["backup"]).is_file())
        text = self.config.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original))
        self.assertIn("[[plugins]]", text)
        self.assertIn('name = "nuclear-dev"', text)
        self.assertIn("added by nuclear-dev-kit register.py", text)

    def test_written_config_parses_as_toml(self) -> None:
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib 需要 Python 3.11+")
        self.write_config('config_version = 12\n')
        completed, _ = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(data["plugins"][0]["name"], "nuclear-dev")
        self.assertEqual(data["plugins"][0]["type"], "stdio")
        self.assertIn("--workspace", data["plugins"][0]["args"])

    def test_duplicate_plugin_is_rejected(self) -> None:
        self.write_config('config_version = 12\n')
        first, _ = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(first.returncode, 0, first.stderr)
        second, payload = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(second.returncode, 2)
        self.assertIn("已存在", payload["error"])
        self.assertEqual(self.config.read_text(encoding="utf-8").count("[[plugins]]"), 1)

    def test_missing_config_is_rejected(self) -> None:
        completed, payload = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("未找到 Reasonix 全局配置", payload["error"])

    def test_default_does_not_write(self) -> None:
        self.write_config('config_version = 12\n')
        completed, payload = self.run_with_home("reasonix", "--scope", "global")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(payload["wrote"])
        self.assertNotIn("[[plugins]]", self.config.read_text(encoding="utf-8"))

    def test_write_leaves_no_temporary_file(self) -> None:
        self.write_config('config_version = 12\n')
        completed, _ = self.run_with_home("reasonix", "--scope", "global", "--write")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        leftovers = [path.name for path in self.home.rglob("*.tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
