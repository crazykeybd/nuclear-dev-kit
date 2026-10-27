#!/usr/bin/env python3
"""MCP 只读面的协议、工具、资源与提示词测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support

READ_ONLY_TOOLS = [
    "nuclear_status",
    "nuclear_gate",
    "nuclear_validate",
    "nuclear_read_artifact",
    "nuclear_schema",
    "nuclear_evidence_list",
]
WRITE_TOOLS = ["nuclear_init", "nuclear_evidence_add", "nuclear_manifest"]


class McpCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.evidence = support.build_valid_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def client(self) -> support.McpClient:
        return support.McpClient([self.root])


class InitializeTest(McpCase):
    def test_initialize_declares_capabilities_and_disciplines(self) -> None:
        with self.client() as client:
            response = client.initialize()
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "nuclear-dev-bot")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("resources", result["capabilities"])
        self.assertIn("prompts", result["capabilities"])
        instructions = result["instructions"]
        self.assertIn("先调用 nuclear_gate", instructions)
        self.assertIn("不得重试", instructions)
        self.assertIn("没有 approve 工具", instructions)
        self.assertIn("不提供批准、授权记忆、凭据读写、删除数据与修改宿主配置", instructions)

    def test_ping(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("ping")
        self.assertEqual(response["result"], {})

    def test_unknown_method_is_reported(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("nuclear/approve", {"stage": "plan"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_parse_error_returns_error_object(self) -> None:
        with self.client() as client:
            assert client.process.stdin is not None
            client.process.stdin.write(b"not-json\n")
            client.process.stdin.flush()
            response = client.read()
        self.assertEqual(response["error"]["code"], -32700)


class ToolListTest(McpCase):
    def test_only_read_only_tools_are_exposed(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("tools/list")
        names = [item["name"] for item in response["result"]["tools"]]
        self.assertEqual(names, READ_ONLY_TOOLS)
        for forbidden in WRITE_TOOLS:
            self.assertNotIn(forbidden, names)
        for name in names:
            self.assertNotIn("approve", name.lower())
            self.assertNotIn("sign", name.lower())

    def test_every_tool_has_object_schema(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("tools/list")
        for tool in response["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["type"], "object", tool["name"])
            self.assertTrue(tool["description"], tool["name"])


class ToolBehaviourTest(McpCase):
    def test_gate_passes_on_valid_project(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_gate", {"stage": "release"})
        self.assertFalse(is_error)
        self.assertTrue(payload["ok"], payload["errors"])
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["rules_version"], support.nuclearlib.KIT_VERSION)
        self.assertEqual(len(payload["kit_sha256"]), 64)

    def test_gate_block_is_a_domain_result_not_a_tool_error(self) -> None:
        (self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["plan"]).unlink()
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_gate", {"stage": "release"})
        self.assertFalse(is_error)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit_code"], 1)
        self.assertTrue(any("前置阶段 plan 未通过" in item for item in payload["errors"]))

    def test_gate_matches_cli_verdict(self) -> None:
        code, cli_payload, _ = support.ctl(self.root, "gate", "release", "--json")
        with self.client() as client:
            client.initialize()
            payload, _ = client.payload("nuclear_gate", {"stage": "release"})
        self.assertEqual(code, 0)
        self.assertEqual(cli_payload["errors"], payload["errors"])

    def test_status_and_validate(self) -> None:
        with self.client() as client:
            client.initialize()
            status, status_error = client.payload("nuclear_status")
            validate, validate_error = client.payload("nuclear_validate")
        self.assertFalse(status_error)
        self.assertTrue(all(record["passed"] for record in status["stages"].values()))
        self.assertFalse(validate_error)
        self.assertEqual(validate["errors"], [])

    def test_read_artifact_and_evidence(self) -> None:
        with self.client() as client:
            client.initialize()
            artifact, artifact_error = client.payload("nuclear_read_artifact", {"stage": "plan"})
            evidence, evidence_error = client.payload("nuclear_evidence_list")
        self.assertFalse(artifact_error)
        self.assertTrue(artifact["exists"])
        self.assertEqual(len(artifact["sha256"]), 64)
        self.assertEqual(artifact["artifact"]["schema_version"], 1)
        self.assertFalse(evidence_error)
        self.assertEqual(evidence["count"], len(support.EVIDENCE_FILES))

    def test_read_missing_artifact_is_not_a_tool_error(self) -> None:
        (self.root / ".nuclear-dev" / support.STAGE_ARTIFACTS["vv"]).unlink()
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_read_artifact", {"stage": "vv"})
        self.assertFalse(is_error)
        self.assertFalse(payload["exists"])

    def test_schema_matches_frozen_core(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_schema", {"stage": "design"})
        self.assertFalse(is_error)
        self.assertEqual(payload["schema"], support.nuclearlib.STAGE_SCHEMAS["design"])

    def test_invalid_stage_is_reported(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_gate", {"stage": "publish"})
        self.assertTrue(is_error)
        self.assertIn("stage", payload["error"])

    def test_unknown_tool_is_a_protocol_error(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.call("nuclear_approve", {"stage": "plan"})
        self.assertEqual(response["error"]["code"], -32602)


class WorkspaceBoundaryTest(McpCase):
    def test_parent_traversal_is_rejected(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_status", {"project": "../.."})
        self.assertTrue(is_error)
        self.assertIn("越出 workspace", payload["error"])

    def test_absolute_project_is_rejected(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_status", {"project": str(self.root)})
        self.assertTrue(is_error)
        self.assertIn("相对路径", payload["error"])

    def test_unknown_workspace_is_rejected(self) -> None:
        with self.client() as client:
            client.initialize()
            payload, is_error = client.payload("nuclear_status", {"workspace": "nope"})
        self.assertTrue(is_error)
        self.assertIn("未知 workspace", payload["error"])

    def test_gate_does_not_write_project_files(self) -> None:
        before = {
            path.relative_to(self.root).as_posix(): support.sha256_file(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }
        with self.client() as client:
            client.initialize()
            client.payload("nuclear_gate", {"stage": "release"})
        after = {
            path.relative_to(self.root).as_posix(): support.sha256_file(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(before, after)


class ResourceTest(McpCase):
    def test_static_resources(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("resources/list")
        uris = [item["uri"] for item in response["result"]["resources"]]
        self.assertIn("nuclear://workflow", uris)
        self.assertIn("nuclear://kit/version", uris)
        for stage in support.STAGES:
            self.assertIn("nuclear://schema/%s" % stage, uris)

    def test_templates_are_declared(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("resources/templates/list")
        templates = [item["uriTemplate"] for item in response["result"]["resourceTemplates"]]
        self.assertEqual(len(templates), 3)
        self.assertTrue(any("stages" in item for item in templates))

    def test_read_workflow_and_schema(self) -> None:
        with self.client() as client:
            client.initialize()
            workflow = client.request("resources/read", {"uri": "nuclear://workflow"})
            schema = client.request("resources/read", {"uri": "nuclear://schema/plan"})
            version = client.request("resources/read", {"uri": "nuclear://kit/version"})
        self.assertIn("七阶段受控工作流", workflow["result"]["contents"][0]["text"])
        self.assertEqual(
            json.loads(schema["result"]["contents"][0]["text"]),
            support.nuclearlib.STAGE_SCHEMAS["plan"],
        )
        payload = json.loads(version["result"]["contents"][0]["text"])
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(len(payload["kit_sha256"]), 64)

    def test_read_project_stage_resource(self) -> None:
        workspace = self.root.name
        uri = "nuclear://project/%s/./stages/plan" % workspace
        with self.client() as client:
            client.initialize()
            response = client.request("resources/read", {"uri": uri})
        artifact = json.loads(response["result"]["contents"][0]["text"])
        self.assertEqual(artifact["project"]["name"], "示例核能软件")

    def test_unknown_resource_returns_resource_not_found(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("resources/read", {"uri": "nuclear://schema/publish"})
        self.assertEqual(response["error"]["code"], -32002)

    def test_project_resource_outside_workspace_is_rejected(self) -> None:
        uri = "nuclear://project/%s/../../stages/plan" % self.root.name
        with self.client() as client:
            client.initialize()
            response = client.request("resources/read", {"uri": uri})
        self.assertEqual(response["error"]["code"], -32002)


class PromptTest(McpCase):
    def test_prompts_cover_entry_and_all_stages(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("prompts/list")
        names = [item["name"] for item in response["result"]["prompts"]]
        self.assertIn("nuclear-dev", names)
        for stage in support.STAGES:
            self.assertIn(support.nuclearlib.STAGE_SKILLS[stage], names)
        self.assertEqual(len(names), 8)

    def test_prompt_reuses_skill_file_without_frontmatter(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("prompts/get", {"name": "nuclear-plan"})
        text = response["result"]["messages"][0]["content"]["text"]
        source = (support.REPO / "skills" / "nuclear-plan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertFalse(text.startswith("---"))
        self.assertTrue(source.endswith(text))
        self.assertIn("软件策划", text)

    def test_unknown_prompt_is_reported(self) -> None:
        with self.client() as client:
            client.initialize()
            response = client.request("prompts/get", {"name": "nuclear-approve"})
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
