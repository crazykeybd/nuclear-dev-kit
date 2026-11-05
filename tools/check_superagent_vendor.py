#!/usr/bin/env python3
"""校验 superagent 副本的完整性与来源追溯（只读）。

- `superagent/` 必须是上游 dsh-superagent 的完整源码副本：关键入口、prompts、skills、
  locale、构建配置与 MIT 许可证都得在；
- 本机产物（node_modules、.artifacts、构建输出 lib）不得入库；
- `superagent/VENDOR.md` 记录的上游提交必须是 40 位 SHA，且与 `EXPECTED_COMMIT` 一致。

退出码：0 一致，1 有不一致。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO / "superagent"
# 副本对应的上游提交；升级副本时同步改这里和 superagent/VENDOR.md。
EXPECTED_COMMIT = "8c32a9dc5d72c033816c6a8110b37f40cf94fba4"

REQUIRED_FILES = [
    "package.json",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "tsdown.config.ts",
    "vitest.config.ts",
    "cordis.patch.yml",
    "LICENSE",
    "README.md",
    "SETUP.md",
    "VENDOR.md",
    "src/index.ts",
    "src/app/sessions.ts",
    "src/app/prompts.ts",
    "prompts/orchestrator.md",
    "prompts/worker.md",
    "prompts/work.md",
    "skills/dsh-superagent-github/SKILL.md",
    "skills/dsh-superagent-feishu/SKILL.md",
    "locale/en.json",
    "locale/zh.json",
    "scripts/dsh-superagent",
]
FORBIDDEN_DIRS = ["node_modules", ".artifacts", "lib", "coverage", ".git"]
COMMIT_LINE = re.compile(r"^\|\s*上游提交\s*\|\s*`?([0-9a-f]{40})`?")


def inspect() -> Dict[str, Any]:
    problems: List[str] = []
    if not VENDOR_DIR.is_dir():
        return {"ok": False, "problems": ["superagent/ 目录不存在"], "commit": None, "files": 0}

    for relative in REQUIRED_FILES:
        if not (VENDOR_DIR / relative).is_file():
            problems.append("缺少 %s" % relative)

    for name in FORBIDDEN_DIRS:
        if (VENDOR_DIR / name).exists():
            problems.append("%s 是上游忽略的本机产物，不得入库" % name)

    files = [path for path in VENDOR_DIR.rglob("*") if path.is_file()]
    crlf = [path.relative_to(VENDOR_DIR).as_posix() for path in files
            if path.suffix in {".ts", ".md", ".json", ".yml"} and b"\r\n" in path.read_bytes()]
    for name in crlf[:5]:
        problems.append("%s 含 CRLF 换行（仓库统一 LF）" % name)

    commit = None
    vendor_doc = VENDOR_DIR / "VENDOR.md"
    if vendor_doc.is_file():
        for line in vendor_doc.read_text(encoding="utf-8").splitlines():
            match = COMMIT_LINE.match(line.strip())
            if match:
                commit = match.group(1)
                break
        if commit is None:
            problems.append("VENDOR.md 未记录 40 位上游提交")
        elif commit != EXPECTED_COMMIT:
            problems.append(
                "VENDOR.md 的提交 %s 与 EXPECTED_COMMIT %s 不一致" % (commit, EXPECTED_COMMIT)
            )
        if "MIT" not in vendor_doc.read_text(encoding="utf-8"):
            problems.append("VENDOR.md 未写明上游许可证")

    manifest = VENDOR_DIR / "package.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("name") != "dsh-superagent":
            problems.append("package.json 的 name 必须是 dsh-superagent（packageRoot() 按名字找根）")
        if data.get("license") != "MIT":
            problems.append("package.json 的 license 必须是 MIT")

    return {
        "ok": not problems,
        "problems": problems,
        "commit": commit,
        "files": len(files),
    }


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_superagent_vendor.py",
        description="校验 superagent 上游副本的完整性与来源追溯；只读，不修改文件。",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)
    result = inspect()
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    elif result["ok"]:
        print("superagent 副本一致：%d 个文件，上游提交 %s" % (result["files"], result["commit"]))
    else:
        for problem in result["problems"]:
            sys.stderr.write("- %s\n" % problem)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
