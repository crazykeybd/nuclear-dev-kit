---
name: nuclear-install
description: nuclear-dev-kit 的便捷安装、升级与部署入口。自动检测宿主，预览后把全部 Skill 安装到 Claude Code、Codex、opencode、Reasonix 或通用 Agent，可顺带初始化项目工作区并验证。用户说“安装这个包”“怎么部署”“升级 Skill”“装到某个宿主”时使用。
license: MIT
metadata:
  version: "0.1.0"
---

# 便捷安装与升级

本 Skill 是 `nuclear-dev-kit` 的安装前端：负责把包内全部 Skill 复制到目标宿主，必要时初始化项目工作区，并调用真实 CLI 验证。它不做工程批准；默认不修改宿主配置或项目源码，只有用户明确确认时才可写入项目级 `.mcp.json`。

## 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 默认 dry-run。**只有用户明确同意写入后**才追加 `--yes`。
- 目标已存在时安装器默认拒绝；只有用户确认覆盖才加 `--force`，安装器会先备份到 `.nuclear-dev-kit-backups/<UTC 时间戳>/`。
- 不得为了“装成功”而修改 `nuclearlib.py`、跳过冲突或删除用户已有 Skill。
- 不得生成、修改或推断 `.nuclear-dev/approvals/*.json`；不存在自动批准。
- 命令无法执行时如实报告，不能把静态复制说成门禁通过。

## 快速路径

```bash
# 1) 预览：自动检测宿主，不写任何文件
python3 <SKILL_DIR>/scripts/quickinstall.py --json

# 2) 用户确认后写入
python3 <SKILL_DIR>/scripts/quickinstall.py --yes --json

# 3) 安装到全部宿主并初始化当前项目，同时做真实检查
python3 <SKILL_DIR>/scripts/quickinstall.py all \
  --scope project --project <项目> --init --verify --yes --json
```

`<SKILL_DIR>` 是本 `SKILL.md` 所在目录，不要依赖当前工作目录。Windows 上把 `python3` 换成 `py -3`。

## MCP 注册（可选）

Skill 只提供工程指令；要让宿主通过确定性工具调用门禁，再注册 MCP 服务端：

```bash
# 生成注册片段：默认只打印，不写任何配置
python3 <SKILL_DIR>/scripts/register.py claude --scope project --project <项目> --json

# 用户确认后合并写入项目级 .mcp.json（写入前备份）
python3 <SKILL_DIR>/scripts/register.py claude --scope project --project <项目> --write --json
```

- 默认只读；需要 `nuclear_init` / `nuclear_evidence_add` / `nuclear_manifest` 时加 `--allow-write`。任何模式都不提供批准。
- 服务端路径优先使用已安装副本；尚未安装时回落到源码路径。
- Codex 只输出 TOML 片段，由用户追加到 `config.toml`；本工具不写 TOML，避免破坏既有配置。
- Reasonix 原生读取项目根 `.mcp.json`；项目级可用 `--write` 合并写入。写入后必须执行 `reasonix mcp enable nuclear-dev` 显式启用；全局范围输出 `[[plugins]]` 片段，需手工追加到 `config.toml`。
- 片段里的 Python 解释器默认取当前解释器，避免 Windows 上 `python3` 落到应用商店别名。

## 操作流程

1. **定位**：解析本文件所在目录为 `SKILL_DIR`，确认 `scripts/quickinstall.py` 存在。
2. **确认三件事**：目标宿主、安装范围（`global` 全机可用 / `project` 仅当前项目）、项目根目录。`auto` 检测失败时，向用户列出 `claude`、`codex`、`opencode`、`reasonix`、`generic`、`all` 让用户选择，不要自行猜测。
3. **预览**：先运行 dry-run，读取 JSON 中的 `host`、`host_source`、`detected_hosts`、`install.targets`、`install.conflicts`。向用户说清会写到哪里、装多少项、有没有冲突。
4. **写入**：用户明确同意后加 `--yes`。有冲突时先报告，只有用户同意覆盖才加 `--force`。`all` 模式按宿主分组写入：某个宿主目录不可写时只回滚该宿主，其余宿主照常安装，结果以 `status: partial` 与 `failures` 呈现。
5. **初始化**（可选）：用户需要受控研发工作区时加 `--init`，默认用项目目录名作为名称、自动推导小写标识；也可用 `--name`、`--id` 指定。已初始化的工作区不会重复创建。
6. **验证**（可选）：加 `--verify` 运行 `status --json` 与 `gate plan --json`，如实转述退出码与阻断项。
7. **收尾**：提醒用户新开宿主会话，让 Skill 目录重新扫描。
8. **MCP 注册**（可选）：用户需要确定性工具调用时，运行 `register.py` 生成片段；只有用户确认后才加 `--write`。Reasonix 全局范围可用 `--write` 追加 `[[plugins]]` 并自动备份；配置写入与服务端握手已验证，但在 Reasonix 会话内的实际工具调用尚未验证。

## 参数

| 参数 | 作用 |
|---|---|
| `host` / `--host` | `auto`（默认）、`claude`、`codex`、`opencode`、`reasonix`、`generic`、`all`；两种写法等价 |
| `--scope` | `global`（默认，本机所有项目）或 `project`（需 `--project`） |
| `--project` | 项目根目录，默认当前目录；`--init` 也使用该目录 |
| `--init` | 安装后初始化 `.nuclear-dev/` 工作区 |
| `--name` / `--id` | 初始化用的项目名与标识；`id` 会被规范为小写字母、数字和连字符 |
| `--verify` | 运行 `status` 与 `gate plan` |
| `--dry-run` | 强制只预览 |
| `--yes` | 确认写入；缺省即 dry-run |
| `--force` | 备份并覆盖已存在的同名 Skill |
| `--json` | 机器可读输出；Skill 内优先使用 |

## 退出码

| 码 | 含义 | 处理 |
|---|---|---|
| `0` | 预览正常结束，或安装（含初始化）成功 | 继续 |
| `1` | 目标冲突或初始化失败 | 读 JSON 的 `error` 与 `install.conflicts`；不要弱化规则 |
| `2` | 参数错误、缺少同包脚本、未检测到宿主、项目目录不存在；或 `all` 模式下部分宿主安装失败 | 前者修正调用方式；后者读 `failures`，如实报告哪些宿主已写入、哪些失败，修复后只重装失败的那个宿主 |

`--verify` 中 `gate plan` 在全新项目返回 `1` 是预期行为，不代表安装失败。

## 安装布局

| 宿主 | `--scope project` | `--scope global` |
|---|---|---|
| Claude Code | `<项目>/.claude/skills` | `~/.claude/skills` |
| Codex | `<项目>/.agents/skills` | `$CODEX_HOME/skills` 或 `~/.codex/skills` |
| opencode | `<项目>/.opencode/skills` | `~/.config/opencode/skills` |
| Reasonix | `<项目>/.reasonix/skills` | `$REASONIX_HOME/skills`；Windows `%APPDATA%\reasonix\skills`；其他 `~/.reasonix/skills` |
| generic | `<项目>/.agents/skills` | `~/.agents/skills` |

`all` 会安装到全部目标，并按绝对路径去重。安装器只替换各个 `nuclear-*` 子目录，不替换整个 `skills/`，并排除 `__pycache__` 与 `*.pyc`。

## 验证安装

1. 每个目标目录都有 `SKILL.md`，全部 Skill 可读。
2. 在工作区运行 `nuclearctl.py --root <项目> status --json`，能返回七阶段状态。
3. 新会话中能调用 `nuclear-plan`；进入后第一件事应是只读检查，而不是直接写文件。

更完整的宿主差异、手动复制、升级与卸载说明见 [references/install-guide.md](references/install-guide.md)。
