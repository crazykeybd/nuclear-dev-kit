#!/usr/bin/env python3
"""一条命令把「核能门禁 + nuclear-dev-agent」部署成一个能用的 DSH profile。

它把 [docs/nuclear-dev-agent.md](../docs/nuclear-dev-agent.md) 里那串手工步骤固化下来，顺序是：

1. 用 pnpm 构建 agent 包 `nuclear-dev-agent/`（已有 `lib/` 时跳过）——它就是本仓库的主体包；
2. 把十个 `nuclear-*` Skill 装到 `$DSH_HOME/skills`——这是 DSH 的用户级 Skill 根，
   所有 profile、所有 Ticket 工作目录都能看到，所以**不需要**再配置 prepare 命令；
3. 建好（或复用）profile，并用 `dsh plugin add link:` 把两个 bundle 链接进去；
4. 把 `dsh.profile.bundles` 补上这两个 bundle（`dsh plugin` 不管这一段）；
5. 写 profile 的 `cordis.patch.yml`：面板端口、stateDir、agent 包跑门禁要用的
   `nuclear.kitPath`（本仓库根的绝对路径）与 `nuclear.python`，以及 `nuclear-dev` 的 MCP 桥接
   （全用绝对路径，因此不需要环境变量）；
6. 用 `dsh --dump-config` 复核生成的树里确实有这些行。

agent 包自己会去调 kit 的命令行，所以 kit 路径必须写进它的配置。`nuclear-dev-agent/` 就是本仓库的
主体包，与 kit 同一个提交，不存在"上游副本"那样的版本漂移。

默认 dry-run，只有 `--yes` 才写文件/跑安装；改动前会备份被改的文件。
它不碰批准、不改目标项目源码、不猜模型供应商——面板里的仓库、账号、允许名单仍需人来填。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
# nuclear-dev-agent/ 是本仓库的主体包，不是上游的只读副本（来源见 nuclear-dev-agent/FORK.md）。
AGENT = REPO / "nuclear-dev-agent"
INSTALLER = REPO / "skills" / "nuclear-setup" / "scripts" / "install.py"
SERVER = REPO / "skills" / "nuclear-dev" / "scripts" / "nuclearmcp.py"
SERVER_NAME = "nuclear-dev"
MCP_ENTRY = "mcp-nuclear-dev"
DEFAULT_PROFILE = "nuclear-dev-agent"
DEFAULT_PORT = 3082
BUNDLES = ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "nuclear-dev-agent", "nuclear-dev-kit"]
PATCH_MARKER = "# === nuclear-dev-kit 部署块：由 tools/deploy_nuclear_dev_agent.py 追加 ==="
# 只有一个空流的 patch（模板 profile 的初始内容）：`[]` 与追加的 `- id:` 不能共存。
EMPTY_FLOW_LIST = re.compile(r"^[ \t]*\[\][ \t]*\n?", re.MULTILINE)
# 三块分开写：已有的 profile 往往已有 webserver 或 nuclear-dev-agent 行，只补缺的那块。
PATCH_BLOCKS = {
    "webserver": """- id: webserver
  config:
    host: 127.0.0.1
    port: %(port)d
""",
    # agent 包自己跑 kit 的门禁命令行，所以除了 stateDir 还要把 kit 路径与解释器告进去。
    "nuclear-dev-agent": """- id: nuclear-dev-agent
  config:
    stateDir: %(state_dir)s
    nuclear:
      kitPath: %(kit)s
      python: %(python)s
""",
    # 核能门禁的 MCP 桥接：绝对路径，所以不需要任何环境变量。
    # kit bundle 自己插入了同 id 的一行，带 `disabled: !!js !process.env.NUCLEAR_DEV_MCP_SERVER`；
    # 这里的覆盖行必须显式写 disabled: false，否则只覆盖 config 会留下「未设环境变量就关闭」。
    MCP_ENTRY: """- id: mcp-nuclear-dev
  name: '@deepseek-ai/dsh-mcp-client'
  disabled: false
  config:
    serverName: nuclear-dev
    transport: stdio
    command: %(python)s
    args:
      - %(server)s
    toolCallTimeoutMs: 60000
    failOnStartupError: false
""",
}


class DeployError(Exception):
    """前置条件或外部命令失败。"""


def dsh_home(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    value = os.environ.get("DSH_HOME")
    base = Path(value).expanduser() if value else Path.home() / ".dsh"
    return base.resolve()


def emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def run(argv: Sequence[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    """跑一条外部命令并合并输出；不抛异常，退出码交给调用方判断。"""
    try:
        completed = subprocess.run(
            [str(item) for item in argv],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return 127, str(exc)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    target = path.with_name("%s.%s.bak" % (path.name, stamp()))
    target.write_bytes(path.read_bytes())
    return str(target)


def plan_build(agent: Path, skip: bool, pnpm: str) -> Dict[str, Any]:
    built = (agent / "lib" / "index.js").is_file()
    if skip or built:
        return {"step": "build", "needed": False, "reason": "已有 lib/ 或 --skip-build", "commands": []}
    if not agent.is_dir() or not (agent / "package.json").is_file():
        raise DeployError(
            "找不到 agent 包目录（%s）；nuclear-dev-agent/ 就是本仓库的主体包，执行 git checkout 恢复它" % agent
        )
    # 预览阶段不因为缺 pnpm 就失败：先把缺什么摆出来，真正执行时才拦。
    missing_tools = [] if shutil.which(pnpm) else [pnpm]
    return {
        "step": "build",
        "needed": True,
        "reason": "nuclear-dev-agent/lib 尚未构建",
        "commands": [[pnpm, "install"], [pnpm, "build"]],
        "missing_tools": missing_tools,
    }


SKILL_NAMES = [
    "nuclear-dev", "nuclear-setup", "nuclear-install", "nuclear-plan", "nuclear-requirements",
    "nuclear-design", "nuclear-implementation", "nuclear-test", "nuclear-vv", "nuclear-release",
]


def present_skills(root: Path) -> List[str]:
    """返回已经装好的 nuclear-* Skill 名（判据：目录里有 SKILL.md）。"""
    return [name for name in SKILL_NAMES if (root / name / "SKILL.md").is_file()]


def plan_skills(root: Path, refresh: bool) -> Dict[str, Any]:
    """装到用户级 Skill 根；已装齐时跳过，装了一半时用 --force 补齐（安装器会先备份）。"""
    done = present_skills(root)
    step: Dict[str, Any] = {
        "step": "skills",
        "target": "dsh 全局范围（$DSH_HOME/skills）",
        "present": done,
        "reason": "用户级 Skill 根让所有 profile 与 Ticket 工作目录都能看到 nuclear-*",
    }
    if len(done) == len(SKILL_NAMES) and not refresh:
        step["needed"] = False
        step["reason"] = "十个 Skill 已在位，跳过（需要重装时加 --refresh）"
        return step
    argv = [sys.executable, str(INSTALLER), "dsh", "--scope", "global", "--yes", "--json"]
    if done:
        argv.insert(-2, "--force")
    step["needed"] = True
    step["command"] = argv
    return step


def plan_profile(profile: str, dsh: str) -> Dict[str, Any]:
    return {
        "step": "profile",
        "needed": True,
        "command": [dsh, profile, "--from-default-profile", "web", "--dump-config"],
        "reason": "profile 不存在时由 DSH 模板创建；已存在则沿用其配置",
    }


def plan_links(profile: str, dsh: str, agent: Path) -> List[Dict[str, Any]]:
    return [
        {
            "step": "link",
            "package": name,
            "command": [dsh, "plugin", "--profile", profile, "add", "link:%s" % path],
        }
        for name, path in (("nuclear-dev-agent", agent), ("nuclear-dev-kit", REPO))
    ]


def merge_bundles(path: Path, dry_run: bool) -> Dict[str, Any]:
    """把两个 bundle 补进 dsh.profile.bundles；其它字段原样保留。"""
    data: Dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise DeployError("%s 不是合法 JSON，拒绝改写: %s" % (path, exc))
    current = ((data.get("dsh") or {}).get("profile") or {}).get("bundles") or []
    missing = [name for name in BUNDLES if name not in current]
    result = {"step": "bundles", "path": str(path), "missing": missing, "backup": None}
    if not missing:
        return result
    data.setdefault("dsh", {}).setdefault("profile", {})["bundles"] = list(current) + missing
    if dry_run:
        return result
    result["backup"] = backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _only_comments_or_empty_list(text: str) -> bool:
    """`text` 是否只有空行、注释和一个空的 `[]` —— 也就是「还没有任何条目」。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "[]":
            return False
    return True


def patch_rows(profile_dir: Path, port: int, state_dir: Path, python: str, dry_run: bool) -> Dict[str, Any]:
    """把缺的三块配置追加到 profile 的 cordis.patch.yml，已有同 id 的行原样保留。

    `nuclear-dev-agent` 块带上 kitPath（本仓库根的绝对路径）与 python：agent 包自己跑 kit 的
    门禁命令行。dry-run 时不写文件，只把将要追加的文本放进 `preview` 供人复核。
    """
    path = profile_dir / "cordis.patch.yml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _only_comments_or_empty_list(text):
        # DSH 新建 profile 时写的是注释加一个空的 `[]`；留着它再追加 `- id:` 就是非法 YAML。
        text = EMPTY_FLOW_LIST.sub("", text)
    values = {
        "port": port,
        "state_dir": str(state_dir),
        "kit": str(REPO),
        "python": python,
        "server": str(SERVER),
    }
    existing_ids = set(re.findall(r"^-\s*id:\s*(\S+)\s*$", text, re.MULTILINE))
    missing = [name for name in PATCH_BLOCKS if name not in existing_ids]
    kept = [name for name in PATCH_BLOCKS if name in existing_ids]
    result: Dict[str, Any] = {
        "step": "patch",
        "path": str(path),
        "missing": missing,
        "kept": kept,
        "backup": None,
    }
    if not missing:
        return result
    appended = "".join(PATCH_BLOCKS[name] % values for name in missing)
    if dry_run:
        result["preview"] = appended
        return result
    if text.strip() and not text.endswith("\n"):
        text += "\n"
    block = ("\n" + PATCH_MARKER + "\n" + appended) if text.strip() else (PATCH_MARKER + "\n" + appended)
    result["backup"] = backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + block, encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploy_nuclear_dev_agent.py",
        description="一条命令部署「核能门禁 + nuclear-dev-agent」到指定 DSH profile。",
        epilog="默认 dry-run；只有 --yes 才写文件、装 Skill、链接 bundle、构建 agent 包。",
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="目标 DSH profile（默认 nuclear-dev-agent）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="面板端口（默认 3082）")
    parser.add_argument("--state-dir", help="nuclear-dev-agent 的状态目录；默认 <DSH_HOME>/state/<profile>")
    parser.add_argument("--dsh-home", help="DSH home；默认 $DSH_HOME 或 ~/.dsh")
    parser.add_argument("--skip-build", action="store_true", help="不构建 nuclear-dev-agent/（要求 lib/ 已存在）")
    parser.add_argument("--refresh", action="store_true", help="即使 Skill 已装齐也强制重装（安装器会先备份）")
    parser.add_argument(
        "--agent-dir",
        help="agent 包目录；默认本仓库的 nuclear-dev-agent/（它就是本仓库的主体包）",
    )
    parser.add_argument("--dsh-bin", default="dsh", help="dsh 可执行文件")
    parser.add_argument("--pnpm-bin", default="pnpm", help="pnpm 可执行文件")
    parser.add_argument("--yes", action="store_true", help="确认执行（缺省即 dry-run）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    return parser


def execute(args: argparse.Namespace) -> Tuple[int, Dict[str, Any]]:
    home = dsh_home(args.dsh_home)
    profile_dir = home / "profiles" / args.profile
    state_dir = Path(args.state_dir).expanduser().resolve() if args.state_dir else home / "state" / args.profile
    python = sys.executable
    dry_run = not args.yes

    payload: Dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "profile": args.profile,
        "profile_dir": str(profile_dir),
        "dsh_home": str(home),
        "state_dir": str(state_dir),
        "skills_root": str(home / "skills"),
        "steps": [],
        "next_steps": [],
    }

    agent = Path(args.agent_dir).expanduser().resolve() if args.agent_dir else AGENT
    build = plan_build(agent, args.skip_build, args.pnpm_bin)
    if not build["needed"] and not (agent / "lib" / "index.js").is_file():
        raise DeployError(
            "nuclear-dev-agent/lib 不存在且要求跳过构建；先执行 cd nuclear-dev-agent && %s install && %s build"
            % (args.pnpm_bin, args.pnpm_bin)
        )
    payload["steps"].append(build)
    payload["steps"].append(plan_skills(home / "skills", args.refresh))
    payload["steps"].append(plan_profile(args.profile, args.dsh_bin))
    payload["steps"].extend(plan_links(args.profile, args.dsh_bin, agent))
    payload["steps"].append(merge_bundles(profile_dir / "package.json", dry_run=True))
    payload["steps"].append(patch_rows(profile_dir, args.port, state_dir, python, dry_run=True))

    if dry_run:
        payload["ok"] = True
        payload.update(_next_steps(args.profile, args.port, home))
        return 0, payload

    if build["needed"]:
        if build.get("missing_tools"):
            raise DeployError(
                "没找到 %s：构建 nuclear-dev-agent 需要 Node.js 22.19+ 或 24+ 与 pnpm。"
                "装好后重跑，或先用 --skip-build 并自行构建。" % "、".join(build["missing_tools"])
            )
        for argv in build["commands"]:
            code, output = run(argv, cwd=agent)
            payload["steps"].append({"step": "ran", "command": argv, "exit": code, "output": output[-2000:]})
            if code != 0:
                raise DeployError("构建 agent 包失败（%s，退出码 %d）：%s" % (" ".join(argv), code, output[-800:]))
        if not (agent / "lib" / "index.js").is_file():
            raise DeployError("构建后仍没有 %s，请检查 tsdown 输出" % (agent / "lib" / "index.js"))

    skills = plan_skills(home / "skills", args.refresh)
    if skills["needed"]:
        code, output = run(skills["command"])
        payload["steps"].append({"step": "skills", "exit": code, "output": output[-2000:]})
        if code != 0:
            raise DeployError("安装 Skill 失败（退出码 %d）：%s" % (code, output[-800:]))
    else:
        payload["steps"].append({"step": "skills", "exit": 0, "output": "已在位，跳过"})

    if not profile_dir.is_dir():
        argv = plan_profile(args.profile, args.dsh_bin)["command"]
        code, output = run(argv)
        payload["steps"].append({"step": "profile", "command": argv, "exit": code, "output": output[-1000:]})
        if not profile_dir.is_dir():
            raise DeployError("profile 创建失败（退出码 %d）：%s" % (code, output[-800:]))

    for link in plan_links(args.profile, args.dsh_bin, agent):
        code, output = run(link["command"])
        payload["steps"].append({"step": "link", "package": link["package"], "exit": code, "output": output[-1000:]})
        if code != 0:
            raise DeployError("链接 %s 失败（退出码 %d）：%s" % (link["package"], code, output[-800:]))

    payload["steps"].append(merge_bundles(profile_dir / "package.json", dry_run=False))
    payload["steps"].append(patch_rows(profile_dir, args.port, state_dir, python, dry_run=False))

    argv = [args.dsh_bin, "--profile", args.profile, "--dump-config"]
    code, output = run(argv)
    if code == 0:
        missing = [row for row in ("nuclear-dev-agent", MCP_ENTRY, "skill-filesystem") if row not in output]
        payload["steps"].append({"step": "verify", "exit": code, "missing_rows": missing})
        if missing:
            raise DeployError("组合后的配置里缺少这些行：%s" % ", ".join(missing))
    else:
        payload["steps"].append({"step": "verify", "exit": code, "output": output[-800:]})
        raise DeployError("dsh --dump-config 失败（退出码 %d）：%s" % (code, output[-800:]))

    payload["ok"] = True
    payload.update(_next_steps(args.profile, args.port, home))
    return 0, payload


def _next_steps(profile: str, port: int, home: Path) -> Dict[str, Any]:
    return {
        "panel_url": "http://127.0.0.1:%d" % port,
        "next_steps": [
            "启动：dsh %s（面板 %s）" % (profile, "http://127.0.0.1:%d" % port),
            "在面板 Sources 里填目标仓库与 agent 账号的 gh 包装器，在 Policy 里填允许名单——这些是人的决定，脚本不代填。",
            "十个 nuclear-* Skill 已装到 %s，所有 Session 与 Ticket 工作目录都能看到，无需再配 prepare 命令。" % (home / "skills"),
            "模型供应商若未配置，用面板 Settings 或在 %s/cordis.patch.yml 里补 llm 行。" % (home / "profiles" / profile),
        ],
    }


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload = execute(args)
    except DeployError as exc:
        payload = {"ok": False, "dry_run": not args.yes, "error": str(exc)}
        if args.json:
            emit(payload)
        else:
            sys.stderr.write("错误: %s\n" % exc)
        return 2
    if args.json:
        emit(payload)
    else:
        _print_human(payload)
    return code


def _print_human(payload: Dict[str, Any]) -> None:
    if payload.get("dry_run"):
        print("预览（未写任何文件）：")
    for step in payload.get("steps", []):
        if step.get("step") == "ran":
            print("  运行 %s → 退出码 %s" % (" ".join(step["command"]), step["exit"]))
        elif step.get("step") == "link":
            print("  链接 %s → 退出码 %s" % (step.get("package"), step.get("exit", "-")))
        elif step.get("step") == "bundles":
            print("  dsh.profile.bundles：%s" % (("需补 " + "、".join(step["missing"])) if step.get("missing") else "已齐"))
        elif step.get("step") == "patch":
            print("  cordis.patch.yml：%s" % (("需补 " + "、".join(step["missing"])) if step.get("missing") else "已齐"))
        elif step.get("step") == "verify":
            print("  复核组合配置：%s" % (("缺行 " + "、".join(step["missing_rows"])) if step.get("missing_rows") else "行都在"))
        elif step.get("commands"):
            print("  %s：%s" % (step["step"], " → ".join(" ".join(argv) for argv in step["commands"])))
        elif step.get("command"):
            print("  %s：%s" % (step["step"], " ".join(step["command"])))
        elif step.get("missing_tools"):
            print("  %s：缺少 %s（执行前需要先装好）" % (step["step"], "、".join(step["missing_tools"])))
        elif step.get("needed") is False:
            print("  %s：跳过（%s）" % (step["step"], step.get("reason", "")))
        else:
            print("  %s：%s" % (step["step"], step.get("target") or step.get("path") or ""))
    if payload.get("ok"):
        for line in payload.get("next_steps", []):
            print("· " + line)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
