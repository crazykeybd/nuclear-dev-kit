#!/usr/bin/env python3
"""从 Desktop/资产库.md 的合并导出重建 process-assets/ 独立 Skill 包。

单一事实源是用户提供的合并文件；本脚本只读它，确定性写出 UTF-8/LF 的 SKILL.md。
用法：python3 tools/split_process_assets.py [--source <路径>] [--check]

SKILL 名含大写（如 p8-release-baseline-A）会按 Agent Skills 规则规范为小写，
原名称记录在 frontmatter 的 metadata.original-name。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("/home/Admin/Desktop/资产库.md")
TARGET = REPO / "process-assets" / "skills"

# 合并导出把 markdown 标题压平为独立短行；这些是文内反复出现的小节标题。
SECTION_LABELS = {
    "用途", "输入（Arguments）", "文档结构", "填写要点", "生成方法", "生成/使用方式",
    "规则内容（单张规则表：序号 | 类型 | 规则）", "自主软件", "二次开发软件",
    "内容要点", "使用方法", "页结构与版式", "页结构与要点", "章节结构", "结构",
    "表格字段", "字段/列", "字段", "取值字典", "关键表格字段", "核心内容",
    "关键点", "格式要求", "质量要求", "目的", "定义", "关键表格字段",
    "审批意见区", "审批流程", "审批步骤", "审批/签署流程", "承诺条款",
    "数据错误详细描述", "基线管理", "建立基线到 tags 库", "接口人", "版本号规则",
    "平台", "三类流程节点", "成果物", "与 A 类的差异", "用例归档", "报告编写",
    "会前准备", "会议流程", "会后", "附件一", "脚本名称 / 版本号", "情况介绍",
    "测试情况", "使用说明", "核心要求", "注意事项", "目录",
    "01 项目前期", "02 软件策划", "03 软件需求分析", "04 软件设计",
    "05 软件编码实现", "06 软件测试", "07 软件验证与确认", "08 软件发布", "09 脚本发布",
    "判定流程（先分类，再转调）", "路由表（阶段关键词 → skill）",
    "分类判定辅助（文件种类/类型）", "参考资料回退词表（不转调，只登记提示）",
}

STAGE_OF = {
    "p1": "plan", "p2": "plan", "p3": "requirements", "p4": "design",
    "p5": "implementation", "p6": "test", "p7": "vv", "p8": "release",
    "p9": "release",
}


def stage_of(name: str) -> str:
    if name.startswith("planning-report-template"):
        return "plan"
    if name.startswith("process-asset-router"):
        return "router"
    prefix = name.split("-", 1)[0]
    return STAGE_OF.get(prefix, "unassigned")


def parse_blocks(text: str) -> List[Tuple[str, str, List[str]]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("name: ")]
    blocks: List[Tuple[str, str, List[str]]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        original = lines[start][len("name: "):].strip()
        description = ""
        if start + 1 < end and lines[start + 1].startswith("description: "):
            description = lines[start + 1][len("description: "):].strip()
        body = lines[start + 2:end]
        blocks.append((original, description, body))
    return blocks


def canonical_name(original: str) -> str:
    return original.lower()


def render(original: str, description: str, body: List[str]) -> bytes:
    lines = [line.rstrip() for line in body]
    # 去掉尾部空行
    while lines and not lines[-1].strip():
        lines.pop()
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in SECTION_LABELS:
            out.append("## " + stripped)
        elif out and stripped.startswith("→ "):
            out.append("### " + stripped)
        else:
            out.append(line)
    # 第一行是标题（如「软件命名规则（p1-...）」）；其余按行输出。
    if out and not out[0].startswith("# "):
        out[0] = "# " + out[0]
    stage = stage_of(original)
    frontmatter = [
        "---",
        "name: %s" % canonical_name(original),
        "description: %s" % description,
        "license: MIT",
        "metadata:",
        '  version: "5.0.0"',
        '  original-name: "%s"' % original,
        '  stage: "%s"' % stage,
        "---",
        "",
    ]
    text = "\n".join(frontmatter + out) + "\n"
    return text.encode("utf-8")


def build(source: Path) -> Dict[str, bytes]:
    blocks = parse_blocks(source.read_text(encoding="utf-8"))
    files: Dict[str, bytes] = {}
    seen = set()
    for original, description, body in blocks:
        if not description:
            raise SystemExit("Skill 缺少 description: %s" % original)
        name = canonical_name(original)
        if name in seen:
            raise SystemExit("Skill 名称重复: %s" % name)
        seen.add(name)
        files["%s/SKILL.md" % name] = render(original, description, body)
    return files


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="从合并导出重建 process-assets 独立 Skill 包。")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="合并导出文件")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = parser.parse_args(argv)
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        sys.stderr.write("找不到源文件: %s\n" % source)
        return 1
    files = build(source)
    if args.check:
        stale = [rel for rel, payload in files.items()
                 if not (TARGET / rel).is_file() or (TARGET / rel).read_bytes() != payload]
        extra = [p.relative_to(TARGET).as_posix() for p in TARGET.glob("*/SKILL.md")
                 if p.relative_to(TARGET).as_posix() not in files]
        if stale or extra:
            sys.stderr.write("process-assets 未同步：缺失/变化 %d，多余 %d\n" % (len(stale), len(extra)))
            return 1
        sys.stdout.write("process-assets 与源一致：%d 个 Skill\n" % len(files))
        return 0
    for rel, payload in files.items():
        target = TARGET / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    sys.stdout.write("已写出 %d 个 Skill 到 %s\n" % (len(files), TARGET))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
