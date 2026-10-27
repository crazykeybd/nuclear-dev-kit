#!/usr/bin/env python3
"""把本地真值投影成 V&V 输入包。

投影包不是原始文件的复制：它按白名单脱敏、改写路径并逐项标注分类。
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import nuclearlib

from .a2a_policy import ExportPolicy, PolicyError, normalize_relative

SCHEMA_VERSION = 1
BUNDLE_MARKER = "manifest.json"
PROJECTION_FILES = {
    "requirements": "requirements.json",
    "design_summary": "design-summary.md",
    "test_summary": "test-summary.json",
    "vv_scope": "vv-scope.json",
}
REQUIRED_ACTIVITY_TYPES = ["code_verification", "solution_verification", "validation"]


class ProjectionError(Exception):
    """投影所需的产物缺失或内容无效。"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return nuclearlib.sha256_file(path)


def _canonical(value: Any) -> str:
    return nuclearlib.canonical_json(value)


def _read_artifact(project: Path, stage: str) -> Dict[str, Any]:
    path = project / ".nuclear-dev" / nuclearlib.STAGE_ARTIFACTS[stage]
    if not path.is_file():
        raise ProjectionError("缺少阶段产物: %s" % path.relative_to(project).as_posix())
    try:
        value = nuclearlib.load_json(path)
    except nuclearlib.NuclearError as exc:
        raise ProjectionError(str(exc))
    if not isinstance(value, dict):
        raise ProjectionError("阶段产物不是对象: %s" % stage)
    return value


def _source(project: Path, stage: str) -> Dict[str, str]:
    relative = ".nuclear-dev/" + nuclearlib.STAGE_ARTIFACTS[stage]
    return {"path": relative, "sha256": _sha256_file(project / relative)}


def project_requirements(project: Path) -> Dict[str, Any]:
    artifact = _read_artifact(project, "requirements")
    items = []
    for requirement in artifact.get("requirements", []):
        items.append(
            {
                "id": requirement.get("id"),
                "title": requirement.get("title"),
                "statement": requirement.get("statement"),
                "priority": requirement.get("priority"),
                "category": requirement.get("category"),
                "verification_method": requirement.get("verification_method"),
                "validation_required": requirement.get("validation_required"),
                "acceptance_criteria": [
                    {
                        "id": criterion.get("id"),
                        "criterion": criterion.get("criterion"),
                        "method": criterion.get("method"),
                        "tolerance": criterion.get("tolerance"),
                        "evidence_kind": criterion.get("evidence_kind"),
                    }
                    for criterion in requirement.get("acceptance_criteria", [])
                ],
            }
        )
    return {"schema_version": SCHEMA_VERSION, "projection": "requirements", "items": items}


def project_design_summary(project: Path) -> str:
    artifact = _read_artifact(project, "design")
    architecture = artifact.get("architecture", {})
    lines = ["# 设计摘要", "", "## 架构", ""]
    overview = architecture.get("overview")
    if overview:
        lines.append("概述: %s" % overview)
        lines.append("")
    for component in architecture.get("components", []):
        lines.append("- %s %s" % (component.get("id"), component.get("name")))
    lines.extend(["", "## 模型", ""])
    for model in artifact.get("models", []):
        lines.append("- %s %s" % (model.get("id"), model.get("name")))
        if model.get("applicability"):
            lines.append("  - 适用范围: %s" % model.get("applicability"))
        assumptions = model.get("assumptions") or []
        if assumptions:
            lines.append("  - 假设: %s" % "；".join(str(item) for item in assumptions))
    lines.extend(
        [
            "",
            "> 本摘要不包含方程、离散格式、稳定性与误差分析；这些属于 C3，需要单独特批。",
            "",
        ]
    )
    return "\n".join(lines)


def project_test_summary(project: Path) -> Dict[str, Any]:
    artifact = _read_artifact(project, "test")
    tests = []
    for test in artifact.get("tests", []):
        tests.append(
            {
                "id": test.get("id"),
                "title": test.get("title"),
                "level": test.get("level"),
                "category": test.get("category"),
                "module_ids": test.get("module_ids", []),
                "requirement_ids": test.get("requirement_ids", []),
                "result": test.get("result"),
                "evidence_count": len(test.get("evidence_ids", [])),
            }
        )
    regression = artifact.get("regression", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "projection": "test_summary",
        "tests": tests,
        "regression": {
            "baseline": regression.get("baseline"),
            "result": regression.get("result"),
            "evidence_count": len(regression.get("evidence_ids", [])),
        },
    }


def project_vv_scope(project: Path) -> Dict[str, Any]:
    requirements = _read_artifact(project, "requirements")
    design = _read_artifact(project, "design")
    selected = []
    for requirement in requirements.get("requirements", []):
        if not requirement.get("validation_required"):
            continue
        selected.append(
            {
                "id": requirement.get("id"),
                "title": requirement.get("title"),
                "statement": requirement.get("statement"),
                "acceptance_criteria": [
                    {
                        "id": criterion.get("id"),
                        "criterion": criterion.get("criterion"),
                        "method": criterion.get("method"),
                        "tolerance": criterion.get("tolerance"),
                        "evidence_kind": criterion.get("evidence_kind"),
                    }
                    for criterion in requirement.get("acceptance_criteria", [])
                ],
            }
        )
    models = [
        {"id": model.get("id"), "name": model.get("name"), "applicability": model.get("applicability")}
        for model in design.get("models", [])
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "projection": "vv_scope",
        "requirements_requiring_validation": selected,
        "required_activity_types": list(REQUIRED_ACTIVITY_TYPES),
        "design_models": models,
        "notes": ["基准题只提供引用标识；数据与参考解实现属于 C3，需要单独特批。"],
    }


def _write_json(path: Path, value: Any) -> None:
    nuclearlib.atomic_write_json(path, value)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def bundle_digest(manifest: Dict[str, Any]) -> str:
    body = {key: value for key, value in manifest.items() if key != "digest"}
    return _sha256_bytes(_canonical(body).encode("utf-8"))


def build_bundle(
    project: Path,
    recipient_name: str,
    policy: ExportPolicy,
    projections: Optional[Sequence[str]] = None,
    raw_entries: Optional[Sequence[Dict[str, Any]]] = None,
    out_root: Optional[Path] = None,
) -> Dict[str, Any]:
    recipient = policy.recipient(recipient_name)
    selected = list(projections) if projections is not None else list(recipient.get("projections", []))
    if not selected:
        raise ProjectionError("没有可用的投影；检查导出策略")
    for name in selected:
        policy.assert_projection_allowed(name, recipient_name)

    outbox = (out_root or (project / ".nuclear-dev" / "a2a" / "outbox")).resolve()
    bundle_id = "B-%s-%s" % (
        nuclearlib.utc_now().replace("-", "").replace(":", "").replace("T", "T"),
        secrets.token_hex(4),
    )
    bundle_dir = outbox / bundle_id
    if bundle_dir.exists():
        raise ProjectionError("投影包目录已存在: %s" % bundle_dir)
    bundle_dir.mkdir(parents=True)

    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "created_at": nuclearlib.utc_now(),
        "recipient": {
            "agent_id": recipient_name,
            "organization": recipient.get("organization"),
        },
        "projections": [],
        "raw_files": [],
        "digest": "",
    }
    scope_label = recipient.get("scope_label")
    if scope_label:
        manifest["recipient"]["scope_label"] = scope_label

    for name in selected:
        filename = PROJECTION_FILES[name]
        destination = bundle_dir / filename
        if name == "requirements":
            _write_json(destination, project_requirements(project))
            stage = "requirements"
        elif name == "design_summary":
            _write_text(destination, project_design_summary(project))
            stage = "design"
        elif name == "test_summary":
            _write_json(destination, project_test_summary(project))
            stage = "test"
        elif name == "vv_scope":
            _write_json(destination, project_vv_scope(project))
            stage = "requirements"
        else:
            raise ProjectionError("未知投影: %s" % name)
        data = destination.read_bytes()
        manifest["projections"].append(
            {
                "name": name,
                "file": filename,
                "class": "C2",
                "sha256": _sha256_bytes(data),
                "size": len(data),
                "sources": [_source(project, stage)],
            }
        )

    for entry in raw_entries or []:
        relative = normalize_relative(entry["path"])
        policy.assert_raw_exportable(relative, recipient_name)
        source = project / relative
        if not source.is_file():
            raise ProjectionError("原始文件不存在: %s" % relative)
        data = source.read_bytes()
        digest = _sha256_bytes(data)
        if digest != entry.get("sha256"):
            raise ProjectionError("原始文件哈希不匹配: %s" % relative)
        destination = bundle_dir / "raw" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        manifest["raw_files"].append(
            {
                "path": relative,
                "file": "raw/" + relative,
                "class": "C3",
                "sha256": digest,
                "size": len(data),
                "authorization_id": entry.get("authorization_id"),
            }
        )

    manifest["digest"] = bundle_digest(manifest)
    _write_json(bundle_dir / BUNDLE_MARKER, manifest)
    return {"bundle_dir": bundle_dir, "manifest": manifest, "digest": manifest["digest"]}


def verify_bundle(bundle_dir: Path) -> Dict[str, Any]:
    bundle_dir = Path(bundle_dir).resolve()
    manifest_file = bundle_dir / BUNDLE_MARKER
    if not manifest_file.is_file():
        return {"ok": False, "errors": ["缺少 manifest.json"], "manifest": None}
    try:
        with manifest_file.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError) as exc:
        return {"ok": False, "errors": ["manifest 无法读取: %s" % exc], "manifest": None}
    errors: List[str] = []
    if not isinstance(manifest, dict):
        return {"ok": False, "errors": ["manifest 不是对象"], "manifest": None}
    expected = bundle_digest(manifest)
    if manifest.get("digest") != expected:
        errors.append("manifest 摘要不匹配")
    expected_files = {BUNDLE_MARKER}
    entries = list(manifest.get("projections", [])) + list(manifest.get("raw_files", []))
    for entry in entries:
        relative = entry.get("file")
        if not isinstance(relative, str):
            errors.append("条目缺少 file")
            continue
        expected_files.add(relative)
        path = bundle_dir / relative
        if not path.is_file():
            errors.append("缺少文件: %s" % relative)
            continue
        data = path.read_bytes()
        if len(data) != entry.get("size"):
            errors.append("大小不匹配: %s" % relative)
        if _sha256_bytes(data) != entry.get("sha256"):
            errors.append("哈希不匹配: %s" % relative)
    actual_files = {
        path.relative_to(bundle_dir).as_posix() for path in bundle_dir.rglob("*") if path.is_file()
    }
    extra = sorted(actual_files - expected_files)
    if extra:
        errors.append("存在清单外文件: %s" % ", ".join(extra))
    return {"ok": not errors, "errors": errors, "manifest": manifest, "digest": manifest.get("digest")}
