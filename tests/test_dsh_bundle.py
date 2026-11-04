#!/usr/bin/env python3
"""DeepSeek Harness（DSH）部署面的回归测试。

覆盖面：
1. bundle 清单 `package.json` 指向的 patch 文件确实存在，版本与其它宿主清单一致；
2. `cordis.patch.yml` 只插入已安装的 `@deepseek-ai/dsh-mcp-client`，未设置
   `NUCLEAR_DEV_MCP_SERVER` 时整行关闭（挂载 bundle 不会因路径缺失而报错），且默认不带写入开关；
3. `register.py dsh` 生成的片段结构正确，其中的命令能真正启动 MCP 服务端；
4. `install.py dsh` 把 Skill 放到 DSH 的两个扫描根。

结构断言不依赖第三方库：先在文本层面校验关键字段，装了 PyYAML 时再用真正的解析器
复核一次层级，保证「文本检查通过但 YAML 不合法」不会漏网。
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

import support

REPO = support.REPO
MANIFEST = REPO / "package.json"
PATCH = REPO / "cordis.patch.yml"
MCP_PACKAGE = "@deepseek-ai/dsh-mcp-client"


def flat_fields(text: str) -> Dict[str, str]:
    """把 patch 片段摊平成「键 → 首个取值」；只用于结构断言，不作为 YAML 解析器。"""
    fields: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.lstrip("- ").strip()
        fields.setdefault(key, value.strip())
    return fields


def parse_with_yaml(text: str) -> List[dict]:
    """按 DSH 的方式解析 `!!js` 标签（表达式保留为字符串）；没有 PyYAML 时返回空列表。"""
    try:
        import yaml
    except ImportError:  # pragma: no cover - 仅在没有 PyYAML 的环境走到
        return []

    class Loader(yaml.SafeLoader):
        pass

    def construct_js(loader, node):
        if isinstance(node, yaml.ScalarNode):
            return {"__jsExpr": loader.construct_scalar(node)}
        raise AssertionError("!!js 只应以标量形式出现")

    Loader.add_constructor("tag:yaml.org,2002:js", construct_js)
    rows = yaml.load(text, Loader=Loader)
    assert isinstance(rows, list), "patch 必须是列表"
    return rows


class DshBundleManifestTest(unittest.TestCase):
    def manifest(self) -> Dict[str, object]:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_declares_bundle_patch(self) -> None:
        manifest = self.manifest()
        self.assertEqual(manifest["name"], "nuclear-dev-kit")
        self.assertEqual(manifest["version"], "0.1.0")
        patch = manifest["dsh"]["bundle"]["patch"]  # type: ignore[index]
        self.assertEqual(patch, "./cordis.patch.yml")
        self.assertTrue((REPO / patch).is_file(), "dsh.bundle.patch 指向的文件不存在")

    def test_version_matches_other_host_manifests(self) -> None:
        version = self.manifest()["version"]
        others = [
            json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")),
            json.loads((REPO / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")),
            json.loads((REPO / "reasonix-plugin.json").read_text(encoding="utf-8")),
        ]
        for other in others:
            self.assertEqual(other["version"], version, other["name"])

    def test_manifest_ships_skills_and_patch(self) -> None:
        files = self.manifest()["files"]  # type: ignore[index]
        self.assertIn("skills", files)
        self.assertIn("cordis.patch.yml", files)


class DshBundlePatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = PATCH.read_text(encoding="utf-8")
        self.fields = flat_fields(self.text)

    def test_patch_inserts_the_mcp_client_only(self) -> None:
        self.assertIn("insert:", self.text)
        self.assertEqual(self.fields["name"].strip("'\""), MCP_PACKAGE)
        self.assertEqual(self.fields["id"], "mcp-nuclear-dev")
        self.assertEqual(self.fields["serverName"], "nuclear-dev")
        self.assertEqual(self.fields["transport"], "stdio")
        # 只插入一行：patch 里不应出现第二个 insert 条目
        self.assertEqual(len(re.findall(r"^\s*- id: ", self.text, re.MULTILINE)), 1)

    def test_row_is_disabled_unless_the_server_path_is_given(self) -> None:
        self.assertIn("NUCLEAR_DEV_MCP_SERVER", self.fields["disabled"])
        self.assertIn("NUCLEAR_DEV_MCP_SERVER", self.fields["args"])

    def test_default_patch_grants_no_write_access(self) -> None:
        self.assertNotIn("--allow-write", self.fields["args"])
        self.assertNotIn("approve", self.text.lower())

    def test_patch_parses_as_yaml_when_pyyaml_is_available(self) -> None:
        rows = parse_with_yaml(self.text)
        if not rows:
            self.skipTest("本机没有 PyYAML，仅做文本层校验")
        self.assertEqual(len(rows), 1)
        row = rows[0]["insert"][0]
        self.assertEqual(row["name"], MCP_PACKAGE)
        self.assertEqual(row["config"]["serverName"], "nuclear-dev")
        self.assertIn("NUCLEAR_DEV_MCP_SERVER", row["disabled"]["__jsExpr"])
        self.assertIn("NUCLEAR_DEV_MCP_SERVER", row["config"]["args"]["__jsExpr"])


class DshRegisterSnippetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.project = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def snippet(self, *argv: str) -> dict:
        completed = support.run_script(
            support.REGISTER, ["dsh"] + list(argv) + ["--project", str(self.project), "--json"]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = support.parse_json(completed.stdout)
        self.assertTrue(payload["ok"], payload)
        return payload

    def test_snippet_shape_without_writing(self) -> None:
        payload = self.snippet("--scope", "project")
        self.assertEqual(payload["format"], "yaml")
        fields = flat_fields(payload["snippet"])
        self.assertEqual(fields["name"].strip("'\""), MCP_PACKAGE)
        self.assertEqual(fields["serverName"], "nuclear-dev")
        self.assertIn("nuclearmcp.py", payload["snippet"])
        self.assertFalse(any(self.project.iterdir()), "默认不得写任何文件")

    def test_snippet_is_valid_yaml_when_pyyaml_is_available(self) -> None:
        payload = self.snippet("--scope", "project")
        rows = parse_with_yaml(payload["snippet"])
        if not rows:
            self.skipTest("本机没有 PyYAML，仅做文本层校验")
        row = rows[0]["insert"][0]
        self.assertEqual(row["config"]["transport"], "stdio")
        self.assertNotIn("--allow-write", row["config"]["args"])

    def test_allow_write_adds_flag(self) -> None:
        payload = self.snippet("--scope", "project", "--allow-write")
        self.assertIn("--allow-write", payload["snippet"])

    def test_snippet_command_starts_a_real_server(self) -> None:
        """片段里的 server 路径与解释器能真的握手；不依赖任何 YAML 解析器。"""
        payload = self.snippet("--scope", "project")
        server = payload["server_path"]
        # 片段是 YAML，Windows 上的反斜杠会被转义，因此按 JSON 转义形式比对。
        self.assertIn(json.dumps(server, ensure_ascii=False), payload["snippet"])
        self.assertIn(json.dumps(payload["python"], ensure_ascii=False), payload["snippet"])
        process = subprocess.Popen(
            [payload["python"], server, "--workspace", str(self.project)],
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


class DshInstallLayoutTest(unittest.TestCase):
    NAMES = 10

    def test_project_scope_writes_dot_dsh_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            code, payload, err = support.run_install(
                project, "dsh", "--scope", "project", "--yes", "--json"
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(payload["status"], "installed")
            self.assertEqual(len(payload["targets"]), self.NAMES)
            for target in payload["targets"]:
                destination = Path(target["destination"])
                self.assertTrue(
                    support.same_path(destination.parent, project / ".dsh" / "skills"), target
                )
                self.assertTrue((destination / "SKILL.md").is_file())

    def test_global_scope_uses_dsh_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = support.child_env()
            env["DSH_HOME"] = temp
            completed = support.run_script(
                support.INSTALL, ["dsh", "--scope", "global", "--json"], env=env
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = support.parse_json(completed.stdout)
            root = Path(temp) / "skills"
            self.assertEqual(len(payload["targets"]), self.NAMES)
            for target in payload["targets"]:
                self.assertTrue(
                    support.same_path(Path(target["destination"]).parent, root), target
                )


if __name__ == "__main__":
    unittest.main()
