#!/usr/bin/env python3
"""生成可复现的发布包与 SHA256SUMS.txt。

确定性约束：
- 文件按归档路径排序；
- 所有条目使用固定时间戳 1980-01-01T00:00:00；
- 固定 Unix 权限位与 create_system；
- 不打包开发期文件（版本库、dist、缓存、方案与工作记录等）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
KIT_NAME = "nuclear-dev-kit"
EXCLUDED_DIRS = {".git", ".github", "dist", "__pycache__", ".nuclear-dev", ".nuclear-dev-kit-backups"}
EXCLUDED_FILES = {
    "方案.md", "开源bot调研方案.md", "工作记录.md", "CLAUDE.md", "bot.md",
    ".gitignore", ".gitattributes",
}
EXCLUDED_SUFFIXES = {".pyc", ".tmp"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
REQUIRED = [
    "INSTALL.md",
    "README.md",
    "skills/nuclear-dev/SKILL.md",
    "skills/nuclear-dev/scripts/nuclearlib.py",
    "skills/nuclear-dev/scripts/nuclearctl.py",
]


class BuildError(Exception):
    """打包前置条件不满足。"""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_version() -> str:
    manifest_file = REPO / ".claude-plugin" / "plugin.json"
    with manifest_file.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise BuildError("插件清单缺少 version: %s" % manifest_file)
    return version


def iter_files(base: Path) -> List[Path]:
    files: List[Path] = []
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_symlink():
            raise BuildError("拒绝打包符号链接: %s" % relative.as_posix())
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        files.append(path)
    return files


def archive_name(relative: str) -> str:
    return relative if relative == "INSTALL.md" else "%s/%s" % (KIT_NAME, relative)


def collect_entries() -> List[Tuple[str, Path]]:
    entries: List[Tuple[str, Path]] = []
    for path in iter_files(REPO):
        relative = path.relative_to(REPO).as_posix()
        entries.append((archive_name(relative), path))
    present = {arcname for arcname, _ in entries}
    missing = [relative for relative in REQUIRED if archive_name(relative) not in present]
    if missing:
        raise BuildError("发布包缺少必需文件:\n" + "\n".join("- " + item for item in missing))
    entries.sort(key=lambda item: item[0])
    return entries


def sums_text(entries: List[Tuple[str, Path]]) -> str:
    lines = ["%s  %s" % (sha256_file(path), arcname) for arcname, path in entries]
    return "".join(line + "\n" for line in lines)


def zip_info(name: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def build(output: Path) -> Dict[str, Any]:
    version = read_version()
    entries = collect_entries()
    sums = sums_text(entries)
    payloads: List[Tuple[str, bytes]] = [(arcname, path.read_bytes()) for arcname, path in entries]
    payloads.append(("SHA256SUMS.txt", sums.encode("utf-8")))
    payloads.sort(key=lambda item: item[0])
    names = [name for name, _ in payloads]
    if len(names) != len(set(names)):
        raise BuildError("归档路径重复: %s" % ", ".join(sorted(names)))

    output.mkdir(parents=True, exist_ok=True)
    archive = output / ("%s-%s.zip" % (KIT_NAME, version))
    temporary = archive.with_name(archive.name + ".tmp")
    with zipfile.ZipFile(str(temporary), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in payloads:
            bundle.writestr(zip_info(name), data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(archive)

    (output / "SHA256SUMS.txt").write_bytes(sums.encode("utf-8"))
    return {
        "ok": True,
        "version": version,
        "archive": str(archive),
        "archive_sha256": sha256_file(archive),
        "sums": str(output / "SHA256SUMS.txt"),
        "files": len(entries),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_dist.py",
        description="生成确定性的 nuclear-dev-kit 发布包与 SHA256SUMS.txt。",
    )
    parser.add_argument("--output", metavar="目录", default=str(REPO / "dist"), help="输出目录；默认 dist")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build(Path(args.output).expanduser().resolve())
    except BuildError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print("已生成发布包: %s" % payload["archive"])
        print("包含文件数: %d" % payload["files"])
        print("归档 SHA256: %s" % payload["archive_sha256"])
        print("校验清单: %s" % payload["sums"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
