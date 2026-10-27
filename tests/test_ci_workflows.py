#!/usr/bin/env python3
"""CI 工作流文件的静态检查。

GitHub Actions 的 `env` 键大小写不敏感：同时写 `http_proxy` 和 `HTTP_PROXY`
会让整个 workflow 失效（Invalid workflow file）。这种错误只能在 Actions 上暴露，
所以这里用标准库做一遍重复键扫描，把它挡在提交之前。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import support

WORKFLOWS = sorted((support.REPO / ".github" / "workflows").glob("*.yml"))
KEY = re.compile(r"^([A-Za-z0-9_.\-]+):(?:\s|$)")
BLOCK_SCALARS = {"|", ">", "|-", "|+", ">-", ">+"}


def duplicate_keys(text: str) -> list[tuple[int, str]]:
    """返回同一层映射中大小写不敏感的重复键：(行号, 键)。"""
    duplicates: list[tuple[int, str]] = []
    active: list[tuple[int, set[str]]] = []   # 当前嵌套路径上的 (缩进, 已出现的键)
    block_indent: int | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if block_indent is not None:
            if indent > block_indent:      # 块标量（run: |）正文，不解析
                continue
            block_indent = None
        stripped = raw.lstrip(" ")
        if stripped.startswith("- "):      # 序列项自成一个映射
            indent += 2
            stripped = stripped[2:]
            while active and active[-1][0] >= indent:
                active.pop()
            active.append((indent, set()))
        match = KEY.match(stripped)
        if not match:
            continue
        while active and active[-1][0] > indent:
            active.pop()
        if not active or active[-1][0] < indent:
            active.append((indent, set()))
        keys = active[-1][1]
        key = match.group(1)
        lowered = key.lower()
        if lowered in keys:
            duplicates.append((number, key))
        else:
            keys.add(lowered)
        value = stripped[match.end():].strip()
        if value in BLOCK_SCALARS:
            block_indent = indent
    return duplicates


class WorkflowTest(unittest.TestCase):
    def test_workflows_exist(self) -> None:
        self.assertTrue(WORKFLOWS, "未找到 .github/workflows/*.yml")

    def test_no_duplicate_keys(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            duplicates = duplicate_keys(text)
            self.assertEqual(
                duplicates,
                [],
                "%s 存在重复键（Actions 的 env 键大小写不敏感）: %s"
                % (path.name, ", ".join("第 %d 行 %s" % item for item in duplicates)),
            )

    def test_workflows_use_lf(self) -> None:
        for path in WORKFLOWS:
            self.assertNotIn(b"\r\n", path.read_bytes(), "%s 含 CRLF 换行" % path.name)


if __name__ == "__main__":
    unittest.main()
