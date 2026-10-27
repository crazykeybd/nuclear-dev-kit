#!/usr/bin/env python3
"""审计链查看与校验。

只读：不追加记录、不修改状态文件、不写批准。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nuclearaudit.py",
        description="查看与校验核能门禁审计链。只读，不修改任何文件。",
    )
    parser.add_argument("--root", default=".", metavar="路径", help="项目根目录，默认为当前目录")
    subparsers = parser.add_subparsers(dest="command", metavar="子命令")

    head = subparsers.add_parser("head", help="输出当前审计链头")
    head.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    verify = subparsers.add_parser("verify", help="校验哈希链与序号连续性")
    verify.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    root = Path(args.root).expanduser().resolve()
    audit_dir = root / ".nuclear-dev" / "audit"

    from nuclearproto.audit import current_head, statement_hint, verify

    if args.command == "head":
        payload = current_head(audit_dir)
        payload["statement_hint"] = statement_hint(payload)
        if args.json:
            emit(payload)
        else:
            print("审计链头: %s" % payload["head"])
            print("序号: %s" % payload["seq"])
            print("建议写入批准 statement: %s" % payload["statement_hint"])
        return 0

    payload = verify(audit_dir)
    if args.json:
        emit(payload)
    else:
        print("记录数: %d" % payload["records"])
        if payload["ok"]:
            print("审计链校验通过。")
        else:
            print("审计链校验未通过，共 %d 项:" % len(payload["errors"]))
            for error in payload["errors"]:
                print("- %s" % error)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
