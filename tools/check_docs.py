#!/usr/bin/env python3
"""文档与内核一致性校验（只读）。

防止"代码改了、文档没改"的静默漂移。校验项：

1. 文档中出现的每个 `nuclear_*` 标识符，必须是 `nuclearproto.surface` 中真实定义的 MCP 工具；
2. `nuclearlib.STAGE_ARTIFACTS` 中的每个阶段产物路径，必须出现在 `artifact-schema.md`；
3. `nuclearlib.STAGES` 中的每个阶段名，必须至少在一份用户文档中出现。

本脚本只读，不修改任何文件，也不触碰冻结内核的判定逻辑。退出码：0 通过，1 有不一致。
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "nuclear-dev" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import nuclearlib  # noqa: E402  （路径注入后才能导入冻结内核）
from nuclearproto import surface  # noqa: E402

TOOL_NAME = re.compile(r'"name":\s*"(nuclear_[a-z0-9_]+)"')
TOOL_USAGE = re.compile(r"\bnuclear_[a-z0-9_]+\b")
SKIP_DOCS = {"工作记录.md", "开源bot调研方案.md"}


def doc_files(extra: List[Path]) -> List[Path]:
    files = [REPO / "README.md", REPO / "INSTALL.md"]
    files.extend(sorted((REPO / "skills").glob("*/SKILL.md")))
    files.extend(sorted((REPO / "skills").glob("*/references/*.md")))
    files.extend(extra)
    return [path for path in files if path.is_file() and path.name not in SKIP_DOCS]


def known_tools() -> List[str]:
    return sorted(set(TOOL_NAME.findall(inspect.getsource(surface))))


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def check_tool_names(files: List[Path], tools: List[str]) -> List[str]:
    known = set(tools)
    problems: List[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for name in sorted(set(TOOL_USAGE.findall(text))):
            if name not in known:
                problems.append(
                    "%s 引用了不存在的工具 %s；已知工具: %s"
                    % (display_path(path), name, ", ".join(tools))
                )
    return problems


def check_artifact_paths() -> List[str]:
    schema_doc = REPO / "skills" / "nuclear-dev" / "references" / "artifact-schema.md"
    text = schema_doc.read_text(encoding="utf-8")
    problems: List[str] = []
    for stage, relative in sorted(nuclearlib.STAGE_ARTIFACTS.items()):
        if relative not in text:
            problems.append(
                "%s 未记录阶段 %s 的产物路径 %s"
                % (schema_doc.relative_to(REPO).as_posix(), stage, relative)
            )
    return problems


def check_stage_coverage(files: List[Path]) -> List[str]:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    problems: List[str] = []
    for stage in nuclearlib.STAGES:
        if stage not in combined:
            problems.append("用户文档中未出现阶段名 %s" % stage)
    return problems


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_docs.py",
        description="校验文档中引用的工具名、阶段名与阶段产物路径与内核一致。只读，不修改文件。",
    )
    parser.add_argument(
        "--extra-doc",
        action="append",
        default=[],
        metavar="路径",
        help="额外纳入校验的文档；可重复。用于 CI 或临时校验。",
    )
    args = parser.parse_args(argv)
    extra = [Path(item).expanduser().resolve() for item in args.extra_doc]
    missing = [str(path) for path in extra if not path.is_file()]
    if missing:
        sys.stderr.write("找不到文档: %s\n" % ", ".join(missing))
        return 1

    files = doc_files(extra)
    tools = known_tools()
    if not tools:
        sys.stderr.write("未能从 surface 中解析出任何工具名\n")
        return 1
    problems: List[str] = []
    problems.extend(check_tool_names(files, tools))
    problems.extend(check_artifact_paths())
    problems.extend(check_stage_coverage(files))

    if problems:
        for item in problems:
            sys.stderr.write("- %s\n" % item)
        return 1

    sys.stdout.write(
        "文档一致：%d 份文档，%d 个工具，%d 个阶段\n"
        % (len(files), len(tools), len(nuclearlib.STAGES))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
