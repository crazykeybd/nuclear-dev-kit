#!/usr/bin/env python3
"""文档与内核一致性校验的回归测试。

覆盖 tools/check_docs.py：工具名、阶段产物路径、阶段名覆盖必须与内核一致。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import support

CHECK_DOCS = support.REPO / "tools" / "check_docs.py"


class DocsConsistencyTest(unittest.TestCase):
    def test_docs_match_kernel(self) -> None:
        completed = support.run_script(CHECK_DOCS, [])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("文档一致", completed.stdout)

    def test_unknown_tool_is_reported(self) -> None:
        """含未知工具名的文档必须让校验失败。"""
        with tempfile.TemporaryDirectory() as temp:
            extra = Path(temp) / "extra.md"
            extra.write_text("本文件引用 nuclear_approve 这个不存在的工具。\n", encoding="utf-8")
            completed = support.run_script(CHECK_DOCS, ["--extra-doc", str(extra)])
        self.assertEqual(completed.returncode, 1)
        self.assertIn("nuclear_approve", completed.stderr)

    def test_missing_extra_doc_is_reported(self) -> None:
        completed = support.run_script(CHECK_DOCS, ["--extra-doc", "does-not-exist.md"])
        self.assertEqual(completed.returncode, 1)
        self.assertIn("找不到文档", completed.stderr)


if __name__ == "__main__":
    unittest.main()
