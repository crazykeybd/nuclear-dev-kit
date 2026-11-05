#!/usr/bin/env python3
"""校验 nuclear-dev-agent 主体包的 fork 完整性与核能集成（只读）。

`nuclear-dev-agent/` 是本仓库的**主体包**（来源与改动见 `nuclear-dev-agent/FORK.md`），
不是上游的只读副本。本工具回答四件事：

1. 包还是那个包：`package.json` 的名字、`src/index.ts` 的插件名、`cordis.patch.yml` 的三个
   insert id、MIT 许可证都得在；旧的只读副本标记 `VENDOR.md` 不得回潮；
2. 核能集成还在：`src/nuclear/`、`src/app/nuclear.ts`、`src/app/views/nuclear.ts`、
   `src/client/nuclear.tsx`、`prompts/nuclear.md` 缺一不可；
3. 身份没漂：包内文本文件里不得再出现上游旧名（`dsh-superagent`、`DSH_SUPERAGENT_`、
   `dshSuperagent`），命中路径按上限列出并给出总数；
4. fork 记得自己的基点：`FORK.md` 里的 40 位上游提交必须与 `EXPECTED_COMMIT` 一致。

`FORK.md` 不参与第 3 条：它要写明上游出处与改名对照，必然出现上游旧名。

扫描基于工作树（含尚未入库的新增核能文件），跳过 `node_modules/`、`lib/`、`.artifacts/`、
`pnpm-lock.yaml` 与二进制文件。

退出码：0 一致，1 有不一致。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO / "nuclear-dev-agent"
# 上游基点提交；跟进上游时同步改这里和 nuclear-dev-agent/FORK.md。
EXPECTED_COMMIT = "8c32a9dc5d72c033816c6a8110b37f40cf94fba4"

# 主体包的身份标识：缺任何一个都说明这不再是一个能被 DSH 装载的 nuclear-dev-agent。
REQUIRED_FILES = [
    "package.json",
    "cordis.patch.yml",
    "LICENSE",
    "FORK.md",
    "src/index.ts",
]
# 核能集成（本仓库相对上游的改动）；缺一个就说明 refactor 没落地。
NUCLEAR_FILES = [
    "src/nuclear/index.ts",
    "src/nuclear/scan.ts",
    "src/app/nuclear.ts",
    "src/app/views/nuclear.ts",
    "src/client/nuclear.tsx",
    "prompts/nuclear.md",
]
INSERT_IDS = ["nuclear-dev-agent", "nuclear-dev-agent-github", "nuclear-dev-agent-feishu"]
# 旧身份：改名前的上游名字，回潮即身份漂移。
OLD_IDENTITY = ["dsh-superagent", "DSH_SUPERAGENT_", "dshSuperagent"]
SKIP_DIRS = {"node_modules", "lib", ".artifacts", ".git", "coverage", "dist"}
SKIP_FILES = {"pnpm-lock.yaml"}
# FORK.md 记录上游出处与改名对照，必然出现上游旧名，故不参与旧名扫描。
PROVENANCE_FILES = {"FORK.md"}
MAX_LISTED = 10

COMMIT = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
COMMIT_LINE = re.compile(r"^.*上游.*?(?<![0-9a-f])([0-9a-f]{40})(?![0-9a-f])", re.MULTILINE)
PLUGIN_NAME = re.compile(r"name\s*=\s*['\"]nuclear-dev-agent['\"]")


def text_files(root: Path) -> Iterator[Tuple[Path, str]]:
    """遍历包内文本文件（跳过本机产物、锁文件、溯源文件与二进制）。"""
    for current, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = Path(current) / filename
            relative = path.relative_to(root)
            if filename in SKIP_FILES or relative.as_posix() in PROVENANCE_FILES:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            try:
                payload = path.read_bytes()
            except OSError:
                continue
            try:
                yield relative, payload.decode("utf-8")
            except UnicodeDecodeError:
                continue  # 二进制文件不参与文本扫描


def find_commit(text: str) -> Optional[str]:
    """从 FORK.md 里取出上游基点提交：优先取写着「上游」的那一行，退而求其次取第一个 40 位 SHA。"""
    match = COMMIT_LINE.search(text)
    if match:
        return match.group(1)
    match = COMMIT.search(text)
    return match.group(0) if match else None


def inspect(root: Optional[Path] = None) -> Dict[str, Any]:
    agent = Path(root) if root is not None else AGENT_DIR
    result: Dict[str, Any] = {
        "ok": False,
        "problems": [],
        "commit": None,
        "files": 0,
        "old_identity": {"count": 0, "paths": []},
    }
    if not agent.is_dir():
        result["problems"].append("nuclear-dev-agent/ 目录不存在")
        return result

    problems: List[str] = result["problems"]
    for relative in REQUIRED_FILES:
        if not (agent / relative).is_file():
            problems.append("缺少 %s" % relative)
    for relative in NUCLEAR_FILES:
        if not (agent / relative).is_file():
            problems.append("缺少核能集成文件 %s" % relative)
    if (agent / "VENDOR.md").exists():
        problems.append("VENDOR.md 是旧只读副本的标记；来源改由 FORK.md 记录")

    index = agent / "src" / "index.ts"
    if index.is_file() and not PLUGIN_NAME.search(index.read_text(encoding="utf-8")):
        problems.append("src/index.ts 未导出 name = 'nuclear-dev-agent'")

    patch = agent / "cordis.patch.yml"
    if patch.is_file():
        text = patch.read_text(encoding="utf-8")
        for identifier in INSERT_IDS:
            if not re.search(r"^\s*-\s*id:\s*%s\s*$" % re.escape(identifier), text, re.MULTILINE):
                problems.append("cordis.patch.yml 缺少 insert id %s" % identifier)

    license_file = agent / "LICENSE"
    if license_file.is_file() and "MIT License" not in license_file.read_text(encoding="utf-8"):
        problems.append("LICENSE 不是 MIT 许可证")

    manifest = agent / "package.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append("package.json 不是合法 JSON: %s" % exc)
            data = {}
        if data.get("name") != "nuclear-dev-agent":
            problems.append("package.json 的 name 必须是 nuclear-dev-agent（packageRoot() 按名字找根）")
        if data.get("license") != "MIT":
            problems.append("package.json 的 license 必须是 MIT")

    fork_doc = agent / "FORK.md"
    if fork_doc.is_file():
        commit = find_commit(fork_doc.read_text(encoding="utf-8"))
        result["commit"] = commit
        if commit is None:
            problems.append("FORK.md 未记录 40 位上游基点提交")
        elif commit != EXPECTED_COMMIT:
            problems.append(
                "FORK.md 的上游基点 %s 与 EXPECTED_COMMIT %s 不一致" % (commit, EXPECTED_COMMIT)
            )

    offenders: List[str] = []
    scanned = 0
    for relative, text in text_files(agent):
        scanned += 1
        if any(token in text for token in OLD_IDENTITY):
            offenders.append(relative.as_posix())
    result["files"] = scanned
    result["old_identity"] = {"count": len(offenders), "paths": offenders[:MAX_LISTED]}
    for path in result["old_identity"]["paths"]:
        problems.append("%s 仍含上游旧名（%s）" % (path, "、".join(OLD_IDENTITY)))
    if len(offenders) > MAX_LISTED:
        problems.append(
            "另有 %d 个文件仍含上游旧名（只列前 %d 个）" % (len(offenders) - MAX_LISTED, MAX_LISTED)
        )

    result["ok"] = not problems
    return result


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_nuclear_dev_agent.py",
        description="校验 nuclear-dev-agent 主体包的 fork 完整性与核能集成；只读，不修改文件。",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument(
        "--path",
        metavar="目录",
        help="待校验的目录；默认本仓库的 nuclear-dev-agent/（用于校对新检出或备份）",
    )
    args = parser.parse_args(argv)
    result = inspect(Path(args.path).expanduser().resolve() if args.path else None)
    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    elif result["ok"]:
        print(
            "nuclear-dev-agent 主体包一致：%d 个文件，上游基点 %s"
            % (result["files"], result["commit"])
        )
    else:
        for problem in result["problems"]:
            sys.stderr.write("- %s\n" % problem)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
