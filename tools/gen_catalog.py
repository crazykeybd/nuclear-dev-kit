#!/usr/bin/env python3
"""生成并校验 `catalog.json`（只读推导，不修改内核）。

单一事实源是 `skills/*/SKILL.md` 的 frontmatter 与冻结内核 `nuclearlib.py`；
`catalog.json` 只是它们的确定性投影，供人读与机器校验使用。

用法：

    python3 tools/gen_catalog.py            # 写出 catalog.json
    python3 tools/gen_catalog.py --check    # 只校验，不一致时退出码 1

输出为 UTF-8、LF、键排序、两空格缩进，因此同一输入必然得到同一字节序列。
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "nuclear-dev" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import nuclearlib  # noqa: E402  （路径注入后才能导入冻结内核）
from nuclearproto import surface  # noqa: E402

CATALOG = REPO / "catalog.json"
SKILLS_ROOT = REPO / "skills"
TOOL_NAME = re.compile(r'"name":\s*"(nuclear_[a-z0-9_]+)"')
WRITE_TOOLS = ("nuclear_init", "nuclear_evidence_add", "nuclear_manifest", "nuclear_a2a_send")


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def parse_frontmatter(text: str, path: Path) -> Dict[str, str]:
    if not text.startswith("---\n"):
        raise SystemExit("缺少 frontmatter: %s" % display_path(path))
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SystemExit("frontmatter 未闭合: %s" % display_path(path))
    fields: Dict[str, str] = {}
    in_metadata = False
    for raw in parts[1].splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            in_metadata = key == "metadata"
            if value.strip():
                fields[key] = value.strip().strip('"')
            continue
        if in_metadata:
            key, _, value = line.strip().partition(":")
            if value.strip():
                fields["metadata." + key.strip()] = value.strip().strip('"')
    return fields


def skill_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        fields = parse_frontmatter(path.read_text(encoding="utf-8"), path)
        name = fields.get("name")
        if not name:
            raise SystemExit("frontmatter 缺少 name: %s" % display_path(path))
        entries.append(
            {
                "name": name,
                "path": display_path(path),
                "description": fields.get("description", ""),
                "license": fields.get("license", ""),
                "version": fields.get("metadata.version", ""),
            }
        )
    return entries


def stage_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for index, stage in enumerate(nuclearlib.STAGES):
        entries.append(
            {
                "order": index + 1,
                "name": stage,
                "artifact": nuclearlib.STAGE_ARTIFACTS[stage],
                "skill": "nuclear-" + stage,
            }
        )
    return entries


def mcp_entries() -> Dict[str, List[str]]:
    names = sorted(set(TOOL_NAME.findall(inspect.getsource(surface))))
    return {
        "tools": [name for name in names if name not in WRITE_TOOLS],
        "write_tools": [name for name in names if name in WRITE_TOOLS],
    }


def build_catalog() -> Dict[str, Any]:
    return {
        "generated_by": "tools/gen_catalog.py",
        "kit": {
            "name": "nuclear-dev-kit",
            "version": nuclearlib.KIT_VERSION,
            "schema_version": nuclearlib.SCHEMA_VERSION,
        },
        "stages": stage_entries(),
        "skills": skill_entries(),
        "mcp": mcp_entries(),
    }


def render(catalog: Dict[str, Any]) -> bytes:
    text = json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_catalog.py",
        description="从 SKILL.md frontmatter 与冻结内核生成 catalog.json；--check 只校验不写。",
    )
    parser.add_argument("--check", action="store_true", help="只校验 catalog.json 是否与当前源一致")
    parser.add_argument("--output", metavar="路径", help="输出路径；默认仓库根 catalog.json")
    args = parser.parse_args(argv)

    target = Path(args.output).expanduser().resolve() if args.output else CATALOG
    payload = render(build_catalog())

    if args.check:
        if not target.is_file():
            sys.stderr.write("catalog.json 不存在: %s\n" % target)
            return 1
        current = target.read_bytes()
        if current != payload:
            sys.stderr.write(
                "catalog.json 已过期：请运行 python3 tools/gen_catalog.py 重新生成\n"
            )
            return 1
        sys.stdout.write("catalog.json 与当前源一致\n")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    sys.stdout.write("已写出 %s\n" % target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
