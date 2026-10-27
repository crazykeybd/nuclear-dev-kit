#!/usr/bin/env python3
"""A2A 导出策略：按接收方分类白名单，默认拒绝。"""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
CLASSES = ["C0", "C1", "C2", "C3"]
PROJECTIONS = {
    "requirements": "C2",
    "design_summary": "C2",
    "test_summary": "C2",
    "vv_scope": "C2",
}
FORBIDDEN_PREFIXES = (
    ".nuclear-dev/approvals/",
    ".nuclear-dev/audit/",
    ".nuclear-dev/a2a/authorizations/",
    ".nuclear-dev/a2a/export-approvals/",
    ".nuclear-dev/a2a/outbox/",
    ".nuclear-dev/a2a/tasks.json",
    ".nuclear-dev/a2a/export-policy.json",
    ".nuclear-dev/a2a/classification.json",
    ".nuclear-dev/evidence/provenance.json",
)
SOURCE_SUFFIXES = (
    ".py",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".f",
    ".f90",
    ".f95",
    ".cu",
    ".rs",
    ".js",
    ".ts",
    ".java",
    ".go",
)
RELATIVE_RE = re.compile(r"^[^/\\:][^\\]*$")


class PolicyError(Exception):
    """策略缺失、格式错误或请求被策略拒绝。"""


def class_index(value: str) -> int:
    if value not in CLASSES:
        raise PolicyError("未知分类: %s" % value)
    return CLASSES.index(value)


def normalize_relative(relative: str) -> str:
    if not isinstance(relative, str) or not relative.strip():
        raise PolicyError("路径必须是非空字符串")
    candidate = relative.replace("\\", "/").strip()
    if candidate.startswith("/") or ":" in candidate.split("/")[0]:
        raise PolicyError("路径必须是项目内相对路径: %s" % relative)
    parts = [part for part in candidate.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise PolicyError("路径不得包含 ..: %s" % relative)
    return "/".join(parts)


class ExportPolicy:
    def __init__(self, data: Dict[str, Any], classification: Optional[Dict[str, Any]] = None) -> None:
        self.data = data
        self.classification = classification or {"schema_version": SCHEMA_VERSION, "entries": []}

    @classmethod
    def load(
        cls,
        project: Path,
        policy_path: Optional[Path] = None,
        classification_path: Optional[Path] = None,
    ) -> "ExportPolicy":
        policy_file = policy_path or (project / ".nuclear-dev" / "a2a" / "export-policy.json")
        if not policy_file.is_file():
            raise PolicyError("未配置导出策略，按默认拒绝处理: %s" % policy_file)
        try:
            with policy_file.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError) as exc:
            raise PolicyError("无法读取导出策略: %s" % exc)
        _validate_policy(data)
        classification_file = classification_path or (
            project / ".nuclear-dev" / "a2a" / "classification.json"
        )
        classification = {"schema_version": SCHEMA_VERSION, "entries": []}
        if classification_file.is_file():
            try:
                with classification_file.open("r", encoding="utf-8") as stream:
                    classification = json.load(stream)
            except (OSError, ValueError) as exc:
                raise PolicyError("无法读取分类附录: %s" % exc)
            _validate_classification(classification)
        return cls(data, classification)

    def recipient(self, name: str) -> Dict[str, Any]:
        recipients = self.data.get("recipients", {})
        if name not in recipients:
            raise PolicyError("接收方不在策略白名单中: %s" % name)
        return recipients[name]

    def projection_allowed(self, projection: str, recipient_name: str) -> bool:
        if projection not in PROJECTIONS:
            raise PolicyError("未知投影: %s" % projection)
        recipient = self.recipient(recipient_name)
        if projection not in recipient.get("projections", []):
            return False
        return class_index(PROJECTIONS[projection]) <= class_index(recipient["max_class"])

    def assert_projection_allowed(self, projection: str, recipient_name: str) -> None:
        if not self.projection_allowed(projection, recipient_name):
            raise PolicyError("接收方 %s 不允许投影 %s" % (recipient_name, projection))

    def classify(self, relative: str) -> Dict[str, Any]:
        path = normalize_relative(relative)
        if _forbidden(path):
            raise PolicyError("该路径禁止外发: %s" % path)
        for entry in self.classification.get("entries", []):
            pattern = entry["path"].replace("\\", "/")
            if path == pattern or fnmatch(path, pattern):
                return {
                    "path": path,
                    "class": entry["class"],
                    "transferable": bool(entry.get("transferable", True)),
                    "note": entry.get("note", ""),
                }
        if path.startswith(".nuclear-dev/stages/") or path.startswith("evidence/") or path == "release/sbom.json":
            return {"path": path, "class": "C2", "transferable": True, "note": ""}
        suffix = Path(path).suffix.lower()
        if suffix in SOURCE_SUFFIXES:
            return {"path": path, "class": "C3", "transferable": True, "note": "源码"}
        return {"path": path, "class": "C3", "transferable": False, "note": "未分类，默认禁止"}

    def assert_raw_exportable(self, relative: str, recipient_name: str) -> Dict[str, Any]:
        recipient = self.recipient(recipient_name)
        if not recipient.get("allow_c3_raw"):
            raise PolicyError("接收方 %s 未启用 C3 原始文件导出" % recipient_name)
        entry = self.classify(relative)
        if entry["class"] != "C3":
            raise PolicyError("只有 C3 原始文件可走特批；%s 属于 %s，请使用投影" % (relative, entry["class"]))
        if not entry["transferable"]:
            raise PolicyError("该文件被标记为不可转让，任何特批均无效: %s" % relative)
        return entry


def _forbidden(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def _validate_policy(data: Any) -> None:
    if not isinstance(data, dict):
        raise PolicyError("策略必须是 JSON 对象")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise PolicyError("策略 schema_version 必须为 %d" % SCHEMA_VERSION)
    if data.get("default") != "deny":
        raise PolicyError("策略 default 必须为 deny")
    recipients = data.get("recipients")
    if not isinstance(recipients, dict) or not recipients:
        raise PolicyError("策略必须至少配置一个接收方")
    for name, entry in recipients.items():
        if not isinstance(name, str) or not name.strip():
            raise PolicyError("接收方名称无效")
        if not isinstance(entry, dict):
            raise PolicyError("接收方 %s 配置必须是对象" % name)
        organization = entry.get("organization")
        if not isinstance(organization, str) or not organization.strip():
            raise PolicyError("接收方 %s 缺少 organization" % name)
        if entry.get("max_class") not in CLASSES:
            raise PolicyError("接收方 %s 的 max_class 无效" % name)
        projections = entry.get("projections")
        if not isinstance(projections, list) or not all(item in PROJECTIONS for item in projections):
            raise PolicyError("接收方 %s 的 projections 无效" % name)
        if not isinstance(entry.get("allow_c3_raw"), bool):
            raise PolicyError("接收方 %s 的 allow_c3_raw 必须是布尔值" % name)
        if entry["allow_c3_raw"] and class_index(entry["max_class"]) < class_index("C3"):
            raise PolicyError("接收方 %s 的 max_class 低于 C3 却允许 C3 原始文件" % name)
        scope_label = entry.get("scope_label")
        if scope_label is not None and not isinstance(scope_label, str):
            raise PolicyError("接收方 %s 的 scope_label 必须是字符串" % name)


def _validate_classification(data: Any) -> None:
    if not isinstance(data, dict):
        raise PolicyError("分类附录必须是 JSON 对象")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise PolicyError("分类附录 schema_version 必须为 %d" % SCHEMA_VERSION)
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise PolicyError("分类附录 entries 必须是数组")
    for entry in entries:
        if not isinstance(entry, dict):
            raise PolicyError("分类条目必须是对象")
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            raise PolicyError("分类条目缺少 path")
        if entry.get("class") not in CLASSES:
            raise PolicyError("分类条目 %s 的 class 无效" % entry.get("path"))
        if "transferable" in entry and not isinstance(entry["transferable"], bool):
            raise PolicyError("分类条目 %s 的 transferable 必须是布尔值" % entry.get("path"))


def describe_recipients(policy: ExportPolicy) -> List[Dict[str, Any]]:
    result = []
    for name, entry in sorted(policy.data.get("recipients", {}).items()):
        result.append(
            {
                "recipient": name,
                "organization": entry.get("organization"),
                "max_class": entry.get("max_class"),
                "projections": entry.get("projections", []),
                "allow_c3_raw": entry.get("allow_c3_raw"),
                "scope_label": entry.get("scope_label"),
            }
        )
    return result
