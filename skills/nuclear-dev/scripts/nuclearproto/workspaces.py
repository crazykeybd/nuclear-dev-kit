#!/usr/bin/env python3
"""workspace 绑定：把调用限制在启动时授权的目录内。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List

from .jsonrpc import ToolError


class WorkspaceError(Exception):
    """启动参数中的 workspace 无效。"""


def _normalize(path: Path) -> str:
    return os.path.normcase(str(path))


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class WorkspaceSet:
    """启动参数给定的一组 workspace；调用方只能提供其内的相对路径。"""

    def __init__(self, entries: Iterable[str]) -> None:
        self._roots: Dict[str, Path] = {}
        for raw in entries:
            if not raw:
                continue
            path = Path(raw).expanduser()
            if not path.exists():
                raise WorkspaceError("workspace 不存在: %s" % raw)
            if not path.is_dir():
                raise WorkspaceError("workspace 不是目录: %s" % raw)
            resolved = path.resolve()
            identifier = resolved.name or "root"
            existing = self._roots.get(identifier)
            if existing is not None and _normalize(existing) != _normalize(resolved):
                raise WorkspaceError("workspace 标识重复: %s" % identifier)
            if existing is not None:
                continue
            self._roots[identifier] = resolved
        if not self._roots:
            raise WorkspaceError("至少需要一个 --workspace")

    def ids(self) -> List[str]:
        return sorted(self._roots)

    def roots(self) -> List[Path]:
        return [self._roots[name] for name in self.ids()]

    def describe(self) -> Dict[str, str]:
        return {name: str(path) for name, path in sorted(self._roots.items())}

    def resolve(self, identifier: str, relative: str = ".") -> Path:
        if identifier not in self._roots:
            raise ToolError("未知 workspace: %s；可用: %s" % (identifier, ", ".join(self.ids())))
        root = self._roots[identifier]
        if not isinstance(relative, str) or not relative:
            raise ToolError("project 必须是非空相对路径字符串")
        if Path(relative).is_absolute() or os.path.isabs(relative):
            raise ToolError("project 必须是相对路径，不能是绝对路径")
        candidate = (root / relative).resolve()
        if not _is_within(root, candidate):
            raise ToolError("project 越出 workspace: %s" % relative)
        return candidate

    def default_id(self) -> str:
        identifiers = self.ids()
        if len(identifiers) != 1:
            raise ToolError("存在多个 workspace，必须显式指定 workspace 参数: %s" % ", ".join(identifiers))
        return identifiers[0]
