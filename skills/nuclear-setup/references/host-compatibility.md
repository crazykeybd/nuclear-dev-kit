# 宿主兼容与安装

## 支持的宿主

| 宿主 | 项目级目录 | 全局目录 |
|---|---|---|
| Claude Code | `.claude/skills` | `~/.claude/skills` |
| Codex | `.agents/skills` | `$CODEX_HOME/skills` 或 `~/.codex/skills` |
| opencode | `.opencode/skills` | `~/.config/opencode/skills` |
| Reasonix | `.reasonix/skills` | `$REASONIX_HOME/skills`；Windows `%APPDATA%\reasonix\skills`；其他 `~/.reasonix/skills` |
| generic | `.agents/skills` | `~/.agents/skills` |

安装器位于 `skills/nuclear-setup/scripts/install.py`，自动解析包含十个 Skill 的源目录。它只复制 Skill，不写宿主配置，不修改项目源码，不生成批准文件。便捷入口 `skills/nuclear-install/scripts/quickinstall.py` 封装了宿主检测、初始化与验证，底层调用同一个安装器。

## 安装命令

```bash
# 便捷路径：自动检测宿主，默认 dry-run
python3 <本包>/skills/nuclear-install/scripts/quickinstall.py --json
python3 <本包>/skills/nuclear-install/scripts/quickinstall.py --yes --json

# 先预览
python3 <本包>/skills/nuclear-setup/scripts/install.py codex \
  --scope project --project <项目> --json

# 确认后安装
python3 <本包>/skills/nuclear-setup/scripts/install.py codex \
  --scope project --project <项目> --yes --json

# 安装到所有宿主的目标路径，按绝对路径去重
python3 <本包>/skills/nuclear-setup/scripts/install.py all \
  --scope project --project <项目> --yes --json
```

默认是 dry-run；只有 `--yes` 且未显式指定 `--dry-run` 才写入。目标已存在时默认以冲突退出（码 `1`），确认覆盖时加 `--force`。覆盖前会在目标 Skill 根目录的 `.nuclear-dev-kit-backups/<UTC 时间戳>/` 下创建备份。

安装器先预检全部目标，再在目标同一文件系统暂存十份 Skill，随后用 `os.replace()` 逐个原子替换；任一步失败会回滚已替换的目标。它只替换十个 Skill 子目录，不替换整个 `skills/`，并排除 `__pycache__` 和 `*.pyc`。

## MCP 注册（可选）

Skill 安装只复制指令与脚本。要让宿主通过确定性工具调用门禁，再用 `skills/nuclear-install/scripts/register.py` 生成注册片段（覆盖 claude / codex / reasonix / generic；opencode 的 MCP 配置格式未实测，调用会返回明确错误）：

```bash
python3 <本包>/skills/nuclear-install/scripts/register.py claude \
  --scope project --project <项目> --json
```

默认只打印，不写宿主配置。Claude Code 与 Reasonix 项目级可加 `--write` 合并 `.mcp.json`，写入前备份；Reasonix 原生读取该文件。Codex 只输出 TOML 片段，由用户追加到 `config.toml`；**Reasonix 全局范围可加 `--write` 自动追加 `[[plugins]]` 到 `config.toml`，写入前备份，同名插件已存在时拒绝重复写入**。默认只读，写入工具需显式 `--allow-write`。

## 调用语法

- Claude Code：`/nuclear-plan`，插件安装后可能带命名空间；也可用 Skill 机制调用。
- Codex：`$nuclear-plan`，或在技能列表中选择。
- opencode：用 `/nuclear-plan` 或宿主提供的 Skill 选择器。
- Reasonix：在 Skill 入口选择，或用自然语言点名“使用 nuclear-plan”。
- 通用代理：直接读取 `skills/nuclear-plan/SKILL.md`，并以文件路径定位 `scripts/nuclearctl.py`。

所有宿主调用同一门禁库，不得为适配某个宿主复制一份弱化版规则。若宿主不支持脚本执行，仍必须显式报告无法运行门禁，不能声称阶段通过。

## 插件清单

- Reasonix：包根 `reasonix-plugin.json`，v2 清单贡献 `skills` 目录。
- Claude Code：`.claude-plugin/plugin.json` 与 `.claude-plugin/marketplace.json`。
- Codex：`.codex-plugin/plugin.json`，`skills` 指向 `./skills/`。
- generic：直接复制 `skills/` 下的十个目录即可。

## 宿主能力限制

| 宿主 | 限制 | 影响 |
|---|---|---|
| Codex | **Skill 正文硬上限 8 KB**（8192 字节，含 frontmatter） | 超限会被截断，指令不完整。任何 SKILL.md 扩写前必须核对字节数 |
| Codex | 上下文文件 `AGENTS.md` 上限 32 KiB | 不适用于本包的 Skill 目录 |
| 各类 | 不保证支持脚本执行 | 无法运行门禁时必须显式报告，不得声称阶段通过 |

当前各 `SKILL.md` 字节数（以 `wc -c` 为准，上限 8192）：

| Skill | 字节 | 距上限 |
|---|---|---|
| nuclear-install | 7271 | 921 |
| nuclear-plan | 6333 | 1859 |
| nuclear-requirements | 6244 | 1948 |
| nuclear-vv | 6115 | 2077 |
| nuclear-implementation | 5990 | 2202 |
| nuclear-design | 5964 | 2228 |
| nuclear-test | 5935 | 2257 |
| nuclear-release | 5810 | 2382 |
| nuclear-dev | 5524 | 2668 |
| nuclear-setup | 2347 | 5845 |

该上限由 `tests/test_skill_limits.py` 在回归测试中强制检查；新增或扩写 SKILL.md 时若超限，测试会失败。

## 环境要求

- Python 3.7.3 或更高版本，仅使用标准库。
- 所有脚本路径从当前 `SKILL.md` 的同级 `scripts/` 推导，不能依赖当前目录。
- 写入采用 UTF-8、LF 换行；JSON 使用稳定的键排序输出。
- 安装器退出码：dry-run 或成功为 `0`，目标冲突为 `1`，参数或工具错误为 `2`。
