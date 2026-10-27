# 安装参考

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| Python | 3.7.3 或更高；只用标准库，无需 pip |
| 网络 | 不需要，可完全离线 |
| 磁盘 | 约 1 MB |
| 操作系统 | Windows / Linux / macOS |

Windows 上 `python3` 可能只是应用商店别名，改用 `py -3`；或安装 python.org 正式版并加入 PATH。

## 2. 前置自检

```bash
python3 <本包>/skills/nuclear-dev/scripts/nuclearctl.py --help
```

应看到 `init`、`status`、`validate`、`gate`、`evidence`、`manifest`，以及阶段顺序
`plan -> requirements -> design -> implementation -> test -> vv -> release`。

冒烟测试（在临时目录，完成后可删除）：

```bash
python3 <本包>/skills/nuclear-dev/scripts/nuclearctl.py \
  --root /tmp/nuclear-smoke init --name "冒烟测试" --id smoke-test --json
```

预期 `ok: true`，并生成 `/tmp/nuclear-smoke/.nuclear-dev/`。

## 3. 安装命令对照

```bash
Q=<SKILL_DIR>/scripts/quickinstall.py

# 自动检测宿主，全局安装（推荐先预览）
python3 "$Q" --json
python3 "$Q" --yes --json

# 指定宿主
python3 "$Q" claude --scope global --yes --json
python3 "$Q" codex --scope project --project <项目> --yes --json

# 覆盖已有安装（先备份）
python3 "$Q" claude --scope global --yes --force --json

# 安装 + 初始化 + 验证
python3 "$Q" claude --scope project --project <项目> --init --verify --yes --json
```

底层安装器为 `../nuclear-setup/scripts/install.py`。参数、冲突处理和退出码与它一致；`quickinstall.py` 只是增加了宿主检测、初始化与验证编排。

## 4. 手动复制（没有 Python 时）

安装器的动作就是把源目录下的各个 `nuclear-*` 目录复制到宿主的 skills 目录：

```bash
mkdir -p <项目>/.claude/skills
cp -r <本包>/skills/nuclear-* <项目>/.claude/skills/
```

注意事项：

- 不要复制整个 `skills/` 目录，只复制其中的 `nuclear-*` 子目录。
- 排除 `__pycache__/` 与 `*.pyc`。
- 没有 Python 时 `nuclearctl.py` 无法运行，门禁也就无法执行；报告中必须写明“无法执行门禁”，不得把静态文件说成门禁通过。

## 5. MCP 注册（可选）

Skill 安装完成后，宿主只是拿到工程指令。若要让宿主通过确定性工具调用门禁，再注册 MCP 服务端：

```bash
R=<SKILL_DIR>/scripts/register.py

# 1) 只打印片段，不写配置（默认）
python3 "$R" claude --scope project --project <项目> --json

# 2) 用户确认后合并写入项目级 .mcp.json（写入前备份）
python3 "$R" claude --scope project --project <项目> --write --json

# 3) 需要写入工具时
python3 "$R" claude --scope project --project <项目> --allow-write --json
```

- 服务端路径优先取宿主 skills 目录里的已安装副本；未安装时回落到源码路径，JSON 的 `server_source` 会标明。
- `command` 默认使用当前 Python 解释器，避免 Windows 上 `python3` 命中应用商店别名。
- Codex 输出 TOML 片段，需要手工追加到 `config.toml`；本工具不写 TOML。
- Reasonix 原生读取项目根 `.mcp.json`，项目级可直接合并写入；写入后执行 `reasonix mcp enable nuclear-dev` 显式启用。全局范围输出 `[[plugins]]` TOML 片段。
- 验证：`reasonix mcp list` 应出现 `nuclear-dev (stdio)`；`reasonix doctor capabilities --live --json` 应显示 `runtime_status=probed`、`tool_count=6`。
- 通用客户端用 `generic`，按宿主文档把 `command` / `args` 映射到 MCP 服务配置。

注册后在新会话里确认：`tools/list` 返回 6 个只读工具（或加 `--allow-write` 时的 9 个），且不存在任何 `approve` 工具。

## 6. 升级与卸载

- **升级**：用新包再跑一次安装器并加 `--yes --force`；备份目录保留旧版本。项目里的 `.nuclear-dev/` 数据不受影响，升级后跑一次 `validate --json` 确认 Schema 兼容。
- **卸载**：删除宿主 skills 目录下的各个 `nuclear-*` 目录。`.nuclear-dev/` 是业务数据，按项目自身配置管理策略处理，不要和 Skill 一起删。
- **回滚**：把 `.nuclear-dev-kit-backups/<UTC 时间戳>/` 下的内容拷回目标 Skill 根目录。

## 7. 常见问题

**`status: conflict`，退出码 1。** 目标已存在。确认覆盖时加 `--force`（先备份）；或先手动删除对应 Skill 目录。

**`status: needs_host`，退出码 2。** 未检测到宿主标记。用 `--host claude|codex|opencode|reasonix|generic|all` 指定。

**`missing_installer` / `missing_cli`。** 只复制了部分目录。重新复制完整的 `skills/` 下的各个 `nuclear-*` 子目录，安装器与门禁 CLI 必须与 Skill 同级保留。

**项目级安装后宿主看不到 Skill。** 项目级目录必须位于宿主打开的项目根目录；重启宿主或新开会话触发重新扫描。

**`gate plan` 直接失败。** 全新项目这是正常的——`plan` 尚无产物。先完成该阶段。

**控制台中文乱码。** 设置 `PYTHONIOENCODING=utf-8`；cmd 另加 `chcp 65001`。

## 8. 安装后验证

```bash
python3 <宿主 skills>/nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <宿主 skills>/nuclear-dev/scripts/nuclearctl.py --root <项目> gate plan --json
```

`status` 始终返回 `0`；`gate plan` 在全新项目返回 `1` 属预期。新会话中调用 `nuclear-plan`，确认其第一动作是只读检查。

若注册了 MCP 面，再确认服务端能启动：

```bash
python3 <宿主 skills>/nuclear-dev/scripts/nuclearmcp.py --workspace <项目>
```

启动信息只写 stderr；stdout 只应出现 JSON-RPC 消息。
