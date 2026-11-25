#!/usr/bin/env python3
"""process-assets 只读查询：列出资产 Skill、按阶段查询、显示单个 Skill。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PACKAGE_ROOT / "skills"
STAGES = ["plan", "requirements", "design", "implementation", "test", "vv", "release"]


def parse_frontmatter(text: str) -> Dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---", 2)
    fields: Dict[str, str] = {}
    in_meta = False
    for line in parts[1].splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            in_meta = key == "metadata"
            if value.strip():
                fields[key] = value.strip().strip('"')
        elif in_meta:
            key, _, value = line.strip().partition(":")
            if value.strip():
                fields["metadata." + key.strip()] = value.strip().strip('"')
    return fields


def entries() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        fields = parse_frontmatter(path.read_text(encoding="utf-8"))
        rows.append({
            "name": path.parent.name,
            "description": fields.get("description", ""),
            "stage": fields.get("metadata.stage", "unassigned"),
            "original_name": fields.get("metadata.original-name", path.parent.name),
            "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        })
    return rows


def emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="过程资产库 Skill 只读查询工具。")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（本工具始终输出 JSON）")
    sub = parser.add_subparsers(dest="command")
    for name, helper in (("list", "列出全部资产 Skill"), ("show", "显示一个资产 Skill 的内容")):
        sub_command = sub.add_parser(name, help=helper)
        sub_command.add_argument("--json", action="store_true", help="同上")
        if name == "show":
            sub_command.add_argument("name", metavar="Skill 名")
    stage = sub.add_parser("stage", help="按七阶段列出资产 Skill")
    stage.add_argument("--json", action="store_true", help="同上")
    stage.add_argument("name", choices=STAGES, metavar="阶段")
    args = parser.parse_args(argv)
    rows = entries()
    if args.command == "list" or not args.command:
        payload = {"ok": True, "command": "list", "count": len(rows), "skills": rows}
    elif args.command == "stage":
        selected = [row for row in rows if row["stage"] == args.name]
        payload = {"ok": True, "command": "stage", "stage": args.name, "count": len(selected), "skills": selected}
    else:
        match = [row for row in rows if row["name"] == args.name]
        if not match:
            emit({"ok": False, "error": "未知 Skill: %s" % args.name})
            return 1
        payload = {"ok": True, "command": "show", "skill": match[0],
                   "body": (PACKAGE_ROOT / match[0]["path"]).read_text(encoding="utf-8")}
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
