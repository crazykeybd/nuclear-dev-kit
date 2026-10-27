#!/usr/bin/env python3
"""核能门禁的 MCP 能力面：工具、资源与提示词。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import nuclearlib

from . import a2a_client, a2a_export, a2a_policy, a2a_projection, auth
from .audit import RULES_SHA256 as KIT_SHA256
from .audit import RULES_VERSION as KIT_VERSION
from .audit import AuditError, AuditLog, warn
from .jsonrpc import ToolError
from .server import resource_not_found
from .workspaces import WorkspaceSet

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILLS_ROOT = SKILL_DIR.parent
REFERENCES = SKILL_DIR / "references"
SCHEMA_VERSION = nuclearlib.SCHEMA_VERSION
STAGES = list(nuclearlib.STAGES)

INSTRUCTIONS = (
    "本服务只提供确定性判定，不产生工程内容，也不授予任何批准。\n"
    "1. 修改任何阶段产物前，先调用 nuclear_gate 检查目标阶段及其前置阶段。\n"
    "2. 门禁阻断是有效判定：必须原样报告 errors，不得重试到“看起来通过”，也不得改写规则绕过。\n"
    "3. 本服务没有 approve 工具，也不会生成、修改或推断 .nuclear-dev/approvals/*.json。"
    "人工批准必须由具备权限的人员在系统之外独立完成。\n"
    "4. 本服务不提供批准、授权记忆、凭据读写、删除数据与修改宿主配置；这些能力不会在任何版本出现。\n"
    "门禁通过不等同监管批准或真实工程合规。"
)

WRITE_INSTRUCTIONS = (
    "本会话已启用写入工具：nuclear_init、nuclear_evidence_add、nuclear_manifest。"
    "它们只写 .nuclear-dev/ 内的产物、证据索引与发布清单，仍然不会生成批准。"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_property() -> Dict[str, Any]:
    return {"type": "string", "enum": STAGES, "description": "阶段名"}


def _workspace_property(workspaces: WorkspaceSet) -> Dict[str, Any]:
    return {
        "type": "string",
        "description": "workspace 标识；只有一个时可省略。可用: " + ", ".join(workspaces.ids()),
    }


def _project_property() -> Dict[str, Any]:
    return {"type": "string", "description": "workspace 内的项目相对路径；默认 ."}


def _stamp(workspace: str, project: Optional[Path] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "rules_version": KIT_VERSION,
        "kit_sha256": KIT_SHA256,
        "schema_version": SCHEMA_VERSION,
        "workspace": workspace,
    }
    if project is not None:
        payload["project_path"] = project.as_posix()
    return payload


def _resolve(workspaces: WorkspaceSet, arguments: Dict[str, Any]) -> Tuple[str, Path]:
    workspace = arguments.get("workspace")
    if workspace is None:
        workspace = workspaces.default_id()
    if not isinstance(workspace, str):
        raise ToolError("workspace 必须是字符串")
    project = arguments.get("project", ".")
    return workspace, workspaces.resolve(workspace, project)


def _require_stage(arguments: Dict[str, Any]) -> str:
    stage = arguments.get("stage")
    if not isinstance(stage, str) or stage not in STAGES:
        raise ToolError("stage 必须是以下之一: " + ", ".join(STAGES))
    return stage


def _state(project: Path) -> Path:
    return project / ".nuclear-dev"


def _read_json(path: Path) -> Any:
    try:
        return nuclearlib.load_json(path)
    except nuclearlib.NuclearError as exc:
        raise ToolError(str(exc))


def _tool_status(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        status = nuclearlib.stage_status(project)
        payload = {"ok": True, "stages": status}
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_status",
        "description": "查看各阶段当前产物状态，不递归检查前置阶段。只返回判定，不授予批准。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
            },
        },
        "handler": handler,
    }


def _tool_gate(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        stage = _require_stage(arguments)
        include = arguments.get("include_dependencies", True)
        if not isinstance(include, bool):
            raise ToolError("include_dependencies 必须是布尔值")
        errors = nuclearlib.stage_gate(project, stage, include_dependencies=include)
        payload = {
            "ok": not errors,
            "stage": stage,
            "include_dependencies": include,
            "errors": errors,
            "exit_code": 0 if not errors else 1,
        }
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_gate",
        "description": (
            "执行阶段门禁并返回阻断项。默认递归检查全部前置阶段。"
            "门禁阻断是正常判定（ok=false），不是工具错误；本工具不授予批准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "stage": _stage_property(),
                "include_dependencies": {
                    "type": "boolean",
                    "description": "是否递归检查前置阶段；默认 true",
                },
            },
            "required": ["stage"],
        },
        "handler": handler,
    }


def _tool_validate(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        errors = nuclearlib.validate_project(project)
        payload = {
            "ok": not errors,
            "errors": errors,
            "exit_code": 0 if not errors else 1,
        }
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_validate",
        "description": "校验工作区结构、阶段产物、证据哈希、追溯与已登记批准。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
            },
        },
        "handler": handler,
    }


def _tool_read_artifact(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        stage = _require_stage(arguments)
        relative = nuclearlib.STAGE_ARTIFACTS[stage]
        path = _state(project) / relative
        if not path.is_file():
            payload = {
                "ok": False,
                "exists": False,
                "stage": stage,
                "path": relative,
                "error": "阶段产物不存在",
            }
            payload.update(_stamp(workspace, project))
            return payload
        artifact = _read_json(path)
        payload = {
            "ok": True,
            "exists": True,
            "stage": stage,
            "path": relative,
            "sha256": _sha256(path),
            "artifact": artifact,
        }
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_read_artifact",
        "description": "读取阶段产物及其当前 SHA-256。产物不存在时返回 exists=false，不是工具错误。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "stage": _stage_property(),
            },
            "required": ["stage"],
        },
        "handler": handler,
    }


def _tool_schema(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        stage = _require_stage(arguments)
        return {
            "ok": True,
            "stage": stage,
            "schema": nuclearlib.STAGE_SCHEMAS[stage],
            "rules_version": KIT_VERSION,
            "kit_sha256": KIT_SHA256,
            "schema_version": SCHEMA_VERSION,
        }

    return {
        "name": "nuclear_schema",
        "description": "返回指定阶段产物的 JSON Schema，用于起草或校验产物结构。",
        "inputSchema": {
            "type": "object",
            "properties": {"stage": _stage_property()},
            "required": ["stage"],
        },
        "handler": handler,
    }


def _tool_evidence_list(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        path = _state(project) / "evidence" / "index.json"
        if not path.is_file():
            payload = {"ok": False, "exists": False, "error": "证据索引不存在"}
            payload.update(_stamp(workspace, project))
            return payload
        index = _read_json(path)
        records = index.get("evidence", []) if isinstance(index, dict) else []
        payload = {"ok": True, "count": len(records), "evidence": records}
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_evidence_list",
        "description": "列出已登记的证据索引。哈希与文件存在性由 nuclear_validate 校验。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
            },
        },
        "handler": handler,
    }


def _tool_init(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        name = arguments.get("name")
        project_id = arguments.get("id")
        for key, value in (("name", name), ("id", project_id)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ToolError("%s 必须是非空字符串" % key)
        try:
            metadata = nuclearlib.init_project(project, name=name, project_id=project_id)
        except nuclearlib.NuclearError as exc:
            raise ToolError(str(exc))
        payload = {"ok": True, "project": metadata}
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_init",
        "description": "初始化项目门禁工作区。只创建工作区结构与空索引，不生成任何产物或批准。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "name": {"type": "string", "description": "项目显示名称；默认取目录名"},
                "id": {"type": "string", "description": "小写项目标识；默认由名称推导"},
            },
        },
        "handler": handler,
    }


def _tool_evidence_add(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        raw = arguments.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("path 必须是非空字符串")
        if Path(raw).is_absolute() or os.path.isabs(raw):
            raise ToolError("path 必须是项目内相对路径，不能是绝对路径")
        candidate = (project / raw).resolve()
        try:
            candidate.relative_to(project.resolve())
        except ValueError:
            raise ToolError("path 越出项目目录: %s" % raw)
        kind = arguments.get("kind")
        producer = arguments.get("producer")
        command = arguments.get("command")
        result = arguments.get("result")
        for key, value in (("kind", kind), ("producer", producer), ("command", command)):
            if not isinstance(value, str) or not value.strip():
                raise ToolError("%s 必须是非空字符串" % key)
        if result not in ("passed", "failed", "observed", "not_applicable"):
            raise ToolError("result 必须为 passed/failed/observed/not_applicable")
        captured_at = arguments.get("captured_at")
        if captured_at is not None and not isinstance(captured_at, str):
            raise ToolError("captured_at 必须是字符串")
        try:
            record = nuclearlib.add_evidence(
                project,
                source=raw,
                kind=kind,
                producer=producer,
                command=command,
                result=result,
                captured_at=captured_at,
            )
        except nuclearlib.NuclearError as exc:
            raise ToolError(str(exc))
        payload = {"ok": True, "evidence": record}
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_evidence_add",
        "description": (
            "登记一个真实存在的项目内证据文件，返回 evidence.id。"
            "不伪造结果，不覆盖已登记路径，不写批准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "path": {"type": "string", "description": "项目内相对路径"},
                "kind": {"type": "string", "description": "证据类型，例如 test-log"},
                "producer": {"type": "string", "description": "真实执行者姓名或组织"},
                "command": {"type": "string", "description": "产生证据的可复现命令或操作说明"},
                "result": {
                    "type": "string",
                    "enum": ["passed", "failed", "observed", "not_applicable"],
                    "description": "实际结果",
                },
                "captured_at": {"type": "string", "description": "ISO-8601 采集时间；默认当前 UTC"},
            },
            "required": ["path", "kind", "producer", "command", "result"],
        },
        "handler": handler,
    }


def _tool_manifest(workspaces: WorkspaceSet):
    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        version = arguments.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ToolError("version 必须是非空字符串")
        force = arguments.get("force", False)
        if not isinstance(force, bool):
            raise ToolError("force 必须是布尔值")
        try:
            destination, manifest = nuclearlib.build_manifest(project, version, force=force)
        except nuclearlib.NuclearError as exc:
            raise ToolError(str(exc))
        payload = {
            "ok": True,
            "path": destination.as_posix(),
            "manifest": manifest,
        }
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_manifest",
        "description": "发布门禁通过后生成确定性软件配置清单。门禁未通过时拒绝生成。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "version": {"type": "string", "description": "语义版本，例如 1.0.0"},
                "force": {"type": "boolean", "description": "覆盖内容不同的同名清单；默认 false"},
            },
            "required": ["version"],
        },
        "handler": handler,
    }


def _tool_a2a_send(workspaces: WorkspaceSet, a2a_context: Dict[str, Any]):
    config = a2a_context["config"]
    store = a2a_context["store"]

    def handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
        workspace, project = _resolve(workspaces, arguments)
        recipient = arguments.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            raise ToolError("recipient 必须是非空字符串")
        bundle_value = arguments.get("bundle")
        if not isinstance(bundle_value, str) or not bundle_value.strip():
            raise ToolError("bundle 必须是项目内相对路径")
        if Path(bundle_value).is_absolute() or os.path.isabs(bundle_value):
            raise ToolError("bundle 必须是相对路径")
        bundle = (project / bundle_value).resolve()
        try:
            bundle.relative_to(project.resolve())
        except ValueError:
            raise ToolError("bundle 越出项目目录")
        token = arguments.get("token")
        if not isinstance(token, str) or not token.strip():
            raise ToolError("token 必须是非空字符串")
        transfer_ref = arguments.get("transfer_ref")
        if transfer_ref is not None and not isinstance(transfer_ref, str):
            raise ToolError("transfer_ref 必须是字符串")
        try:
            verification = a2a_projection.verify_bundle(bundle)
            if not verification["ok"]:
                raise ToolError("投影包校验失败: " + "; ".join(verification["errors"]))
            manifest = verification["manifest"]
            if manifest.get("recipient", {}).get("agent_id") != recipient:
                raise ToolError("投影包接收方与 recipient 不一致")
            if manifest.get("raw_files"):
                raise ToolError("C3 原始文件只能从 CLI 发送；MCP 仅允许 C2 投影包")
            peer = a2a_client.get_peer(config, recipient)
            ref = transfer_ref or manifest.get("bundle_id")
            a2a_export.consume_authorization(project, token, bundle, recipient)
            card = a2a_client.fetch_card(peer, config)
            result = a2a_client.send_task(peer, store, card, bundle, ref)
        except (
            a2a_client.ClientError,
            a2a_export.ExportError,
            auth.AuthError,
            a2a_policy.PolicyError,
        ) as exc:
            raise ToolError(str(exc))
        payload = {
            "ok": True,
            "recipient": recipient,
            "task": result.get("task"),
            "bundle_id": manifest.get("bundle_id"),
            "bundle_digest": verification["digest"],
            "transfer_ref": ref,
            "card_sha256": result.get("card_sha256"),
        }
        payload.update(_stamp(workspace, project))
        return payload

    return {
        "name": "nuclear_a2a_send",
        "description": (
            "发送 C2 投影包给已配置的 V&V 对端。需要一次性令牌；"
            "C3 原始文件只能从 CLI 发送；本工具不生成令牌，也不修改批准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": _workspace_property(workspaces),
                "project": _project_property(),
                "recipient": {"type": "string", "description": "A2A 配置中的 peer 标识"},
                "bundle": {"type": "string", "description": "项目内投影包相对路径"},
                "token": {"type": "string", "description": "authorize 生成的一次性令牌"},
                "transfer_ref": {"type": "string", "description": "带外引用；默认使用 bundle_id"},
            },
            "required": ["recipient", "bundle", "token"],
        },
        "handler": handler,
    }


# --- 审计 -----------------------------------------------------------

STATE_CHANGING_TOOLS = {"nuclear_init", "nuclear_evidence_add", "nuclear_manifest", "nuclear_a2a_send"}


def _audit_record(
    log: AuditLog,
    tool: str,
    workspace: str,
    project: Path,
    arguments: Dict[str, Any],
    phase: str,
    payload: Optional[Dict[str, Any]] = None,
    is_error: bool = False,
    duration_ms: Optional[int] = None,
) -> None:
    log.append(
        tool=tool,
        workspace=workspace,
        project_path=project.as_posix(),
        arguments=arguments,
        phase=phase,
        ok=payload.get("ok") if isinstance(payload, dict) else None,
        is_error=is_error,
        exit_code=payload.get("exit_code") if isinstance(payload, dict) else None,
        duration_ms=duration_ms,
    )


def _best_effort_result(
    log: AuditLog,
    tool: str,
    workspace: str,
    project: Path,
    arguments: Dict[str, Any],
    started: float,
) -> None:
    try:
        _audit_record(
            log,
            tool,
            workspace,
            project,
            arguments,
            "result",
            None,
            True,
            int((time.time() - started) * 1000),
        )
    except AuditError as exc:
        warn("失败调用的结果审计写入失败（已降级）: %s" % exc)


def _audited(
    tool: str,
    handler: Callable[[Dict[str, Any]], Any],
    workspaces: WorkspaceSet,
    sinks: List[Dict[str, Any]],
    context: Dict[str, Any],
):
    def wrapper(arguments: Dict[str, Any]) -> Any:
        workspace, project = _resolve(workspaces, arguments)
        state_changing = tool in STATE_CHANGING_TOOLS
        state_dir = _state(project)
        if not state_changing and not state_dir.is_dir():
            return handler(arguments)
        log = AuditLog(
            state_dir / "audit",
            actor=str(context.get("client") or "unknown"),
            sinks=sinks,
        )
        started = time.time()
        if state_changing:
            try:
                _audit_record(log, tool, workspace, project, arguments, "intent")
            except AuditError as exc:
                raise ToolError("审计写入失败，操作已中止: %s" % exc)
        try:
            payload = handler(arguments)
        except ToolError:
            _best_effort_result(log, tool, workspace, project, arguments, started)
            raise
        except Exception:
            _best_effort_result(log, tool, workspace, project, arguments, started)
            raise
        duration = int((time.time() - started) * 1000)
        try:
            _audit_record(log, tool, workspace, project, arguments, "result", payload, False, duration)
        except AuditError as exc:
            if state_changing:
                raise ToolError("操作已执行，但结果审计写入失败；请先检查审计日志再继续: %s" % exc)
            warn("审计写入失败（只读调用，已降级）: %s" % exc)
        return payload

    return wrapper


def build_tools(
    workspaces: WorkspaceSet,
    allow_write: bool = False,
    audit_sinks: Optional[List[Dict[str, Any]]] = None,
    audit_context: Optional[Dict[str, Any]] = None,
    a2a_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    tools = [
        _tool_status(workspaces),
        _tool_gate(workspaces),
        _tool_validate(workspaces),
        _tool_read_artifact(workspaces),
        _tool_schema(workspaces),
        _tool_evidence_list(workspaces),
    ]
    if allow_write:
        tools.extend(
            [
                _tool_init(workspaces),
                _tool_evidence_add(workspaces),
                _tool_manifest(workspaces),
            ]
        )
        if a2a_context is not None:
            tools.append(_tool_a2a_send(workspaces, a2a_context))
        context = audit_context if audit_context is not None else {}
        for tool in tools:
            if tool["name"] == "nuclear_schema":
                continue
            tool["handler"] = _audited(
                tool["name"],
                tool["handler"],
                workspaces,
                list(audit_sinks or []),
                context,
            )
    return tools


# --- 资源 -----------------------------------------------------------

def _static_resources() -> List[Dict[str, Any]]:
    resources = [
        {
            "uri": "nuclear://workflow",
            "name": "七阶段工作流",
            "description": "阶段顺序、证据纪律与失败处置规则",
            "mimeType": "text/markdown",
        },
        {
            "uri": "nuclear://kit/version",
            "name": "工具包版本",
            "description": "工具包版本、规则版本与规则哈希",
            "mimeType": "application/json",
        },
    ]
    for stage in STAGES:
        resources.append(
            {
                "uri": "nuclear://schema/%s" % stage,
                "name": "%s 阶段 Schema" % stage,
                "description": "阶段产物 JSON Schema",
                "mimeType": "application/json",
            }
        )
    return resources


def _templates() -> List[Dict[str, Any]]:
    return [
        {
            "uriTemplate": "nuclear://project/{workspace}/{project}/stages/{stage}",
            "name": "阶段产物",
            "description": "读取某个项目的阶段产物",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "nuclear://project/{workspace}/{project}/traceability",
            "name": "追溯图",
            "description": "读取某个项目的追溯节点与关系",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "nuclear://project/{workspace}/{project}/evidence",
            "name": "证据索引",
            "description": "读取某个项目的证据索引",
            "mimeType": "application/json",
        },
    ]


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _split_project_uri(rest: str) -> Tuple[str, str, str, Optional[str]]:
    parts = rest.split("/")
    if len(parts) < 4 or parts[0] != "project":
        raise resource_not_found("nuclear://" + rest)
    workspace = parts[1]
    tail = parts[2:]
    if len(tail) >= 2 and tail[-2] == "stages":
        project_parts, kind, stage = tail[:-2], "stage", tail[-1]
    elif tail[-1] in ("traceability", "evidence"):
        project_parts, kind, stage = tail[:-1], tail[-1], None
    else:
        raise resource_not_found("nuclear://" + rest)
    project = "/".join(project_parts) or "."
    return workspace, project, kind, stage


def build_resource_loader(workspaces: WorkspaceSet):
    def loader(uri: str) -> Dict[str, str]:
        if not uri.startswith("nuclear://"):
            raise resource_not_found(uri)
        rest = uri[len("nuclear://") :]
        if rest == "workflow":
            path = REFERENCES / "workflow.md"
            if not path.is_file():
                raise resource_not_found(uri)
            return {"mimeType": "text/markdown", "text": path.read_text(encoding="utf-8")}
        if rest == "kit/version":
            return {
                "mimeType": "application/json",
                "text": _json_text(
                    {
                        "kit_version": KIT_VERSION,
                        "rules_version": KIT_VERSION,
                        "schema_version": SCHEMA_VERSION,
                        "kit_sha256": KIT_SHA256,
                        "stages": STAGES,
                    }
                ),
            }
        if rest.startswith("schema/"):
            stage = rest[len("schema/") :]
            if stage not in STAGES:
                raise resource_not_found(uri)
            return {
                "mimeType": "application/json",
                "text": _json_text(nuclearlib.STAGE_SCHEMAS[stage]),
            }
        workspace, project_relative, kind, stage = _split_project_uri(rest)
        try:
            project = workspaces.resolve(workspace, project_relative)
        except ToolError as exc:
            raise resource_not_found("%s (%s)" % (uri, exc))
        state = _state(project)
        if kind == "stage":
            if stage not in STAGES:
                raise resource_not_found(uri)
            path = state / nuclearlib.STAGE_ARTIFACTS[stage]
        elif kind == "traceability":
            path = state / "traceability.json"
        else:
            path = state / "evidence" / "index.json"
        if not path.is_file():
            raise resource_not_found(uri)
        return {"mimeType": "application/json", "text": _json_text(_read_json(path))}

    return loader


# --- 提示词 ---------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1 :]).lstrip("\n")
    return text


def _prompt_metadata() -> List[Dict[str, Any]]:
    prompts = [
        {
            "name": "nuclear-dev",
            "description": "七阶段研发总入口：路由、边界与启动顺序",
        }
    ]
    for stage, skill in nuclearlib.STAGE_SKILLS.items():
        prompts.append(
            {
                "name": skill,
                "description": "%s阶段工程指令（来自 SKILL.md）" % nuclearlib.STAGE_LABELS[stage],
            }
        )
    return prompts


def build_prompt_loader():
    def loader(name: str) -> str:
        skill_dir = SKILLS_ROOT / name
        path = skill_dir / "SKILL.md"
        if not path.is_file():
            raise ToolError("提示词来源不存在: %s" % path)
        return _strip_frontmatter(path.read_text(encoding="utf-8"))

    return loader


def build_surface(
    workspaces: WorkspaceSet,
    allow_write: bool = False,
    audit_sinks: Optional[List[Dict[str, Any]]] = None,
    audit_context: Optional[Dict[str, Any]] = None,
    a2a_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    instructions = INSTRUCTIONS if not allow_write else INSTRUCTIONS + "\n" + WRITE_INSTRUCTIONS
    if allow_write and a2a_context is not None:
        instructions += (
            "\n本会话已启用 nuclear_a2a_send：只允许 C2 投影包，必须提供一次性令牌；"
            "C3 原始文件只能从命令行发送。"
        )
    context = audit_context if audit_context is not None else {}
    return {
        "instructions": instructions,
        "audit_context": context,
        "tools": build_tools(
            workspaces,
            allow_write=allow_write,
            audit_sinks=audit_sinks,
            audit_context=context,
            a2a_context=a2a_context,
        ),
        "resources": _static_resources(),
        "templates": _templates(),
        "prompts": _prompt_metadata(),
        "prompt_loader": build_prompt_loader(),
        "resource_loader": build_resource_loader(workspaces),
    }
