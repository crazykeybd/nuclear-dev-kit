#!/usr/bin/env python3
"""宿主能力矩阵一致性的回归测试。

覆盖 tools/check_hosts.py 与 register.py 的 opencode 显式拒绝。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import support

CHECK_HOSTS = support.REPO / "tools" / "check_hosts.py"
REGISTER = support.REGISTER


def load_check_hosts():
    spec = importlib.util.spec_from_file_location("check_hosts_module", str(CHECK_HOSTS))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HostsConsistencyTest(unittest.TestCase):
    def test_hosts_are_consistent(self) -> None:
        completed = support.run_script(CHECK_HOSTS, [])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("宿主矩阵一致", completed.stdout)

    def test_diff_detects_missing_host(self) -> None:
        module = load_check_hosts()
        problems = module.diff(
            "project",
            "install",
            {"claude": ".claude/skills", "codex": ".agents/skills"},
            "register",
            {"claude": ".claude/skills"},
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("codex", problems[0])

    def test_diff_detects_path_mismatch(self) -> None:
        module = load_check_hosts()
        problems = module.diff(
            "project",
            "install",
            {"claude": ".claude/skills"},
            "register",
            {"claude": ".claude/agents"},
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("路径不一致", problems[0])

    def test_register_rejects_unverified_opencode(self) -> None:
        completed = support.run_script(REGISTER, ["opencode", "--project", ".", "--json"])
        self.assertEqual(completed.returncode, 2)
        self.assertIn("未在本包中实测", completed.stdout)


if __name__ == "__main__":
    unittest.main()
