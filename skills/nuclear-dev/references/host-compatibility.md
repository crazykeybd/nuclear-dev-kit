# 宿主兼容与安装

## 支持的宿主

| 宿主 | 项目级目录 | 全局目录 |
|---|---|---|
| Claude Code | `.claude/skills` | `~/.claude/skills` |
| Codex | `.agents/skills` | `$CODEX_HOME/skills` 或 `~/.codex/skills` |
| opencode | `.opencode/skills` | `~/.config/opencode/skills` |
| Reasonix | `.reasonix/skills` | `$REASONIX_HOME/skills`；Windows `%APPDATA%\reasonix\skills`；其他 `~/.reasonix/skills` |
| generic | `.agents/skills` | `~/.agents/skills` |

安装器位于 `skills/nuclear-setup/scripts/install.py`，源目录是包含十个 Skill 的 `skills/` 目录。安装器只复制 Skill，不写宿主配置，不修改项目源码，不生成批准文件。便捷入口 `skills/nuclear-install/scripts/quickinstall.py` 在此基础上增加宿主自动检测、初始化与验证编排，底层仍调用同一个安装器。

## 安装命令

```bash
# 便捷路径：自动检测宿主，默认 dry-run
python3 <本包>/skills/nuclear-install/scripts/quickinstall.py --json
python3 <本包>/skills/nuclear-install/scripts/quickinstall.py --yes --json

# 先预览
python3 <本包>/skills/nuclear-setup/scripts/install.py codex --scope project --project <项目> --json

# 确认后安装
python3 <本包>/skills/nuclear-setup/scripts/install.py codex --scope project --project <项目> --yes --json

# 安装到所有宿主的目标路径，按绝对路径去重
python3 <本包>/skills/nuclear-setup/scripts/install.py all --scope project --project <项目> --yes --json
```

默认是 dry-run；只有 `--yes` 且未显式指定 `--dry-run` 才写入。目标已存在时默认以冲突退出（码 `1`），确认覆盖时加 `--force`，覆盖前会创建 UTC 时间戳备份。安装器先预检全部目标，避免部分安装。

## 调用语法

- Claude Code：`/nuclear-plan`，插件安装后可能带命名空间；也可用 Skill 机制调用。
- Codex：`$nuclear-plan`，或在技能列表中选择。
- opencode：用 `/nuclear-plan` 或宿主提供的 Skill 选择器。
- Reasonix：在 Skill 入口选择，或用自然语言点名“使用 nuclear-plan”。
- 通用代理：直接读取 `skills/nuclear-plan/SKILL.md`，并以文件路径定位 `scripts/nuclearctl.py`。

所有宿主调用同一门禁库，不得为适配某个宿主复制一份弱化版规则。若宿主不支持脚本执行，仍必须显式报告无法运行门禁，不能声称阶段通过。

## 插件清单

- Reasonix：仓库根 `reasonix-plugin.json`，v2 清单贡献 `skills` 目录。
- Claude Code：`.claude-plugin/plugin.json` 与 `.claude-plugin/marketplace.json`。
- Codex：`.codex-plugin/plugin.json`，`skills` 指向 `./skills/`。
- generic：直接复制 `skills/` 下的目录即可。

## MCP 与 A2A

- MCP 注册片段由 `skills/nuclear-install/scripts/register.py` 生成；默认只打印。Claude Code 项目级与 Reasonix 项目级可用 `--write` 合并 `.mcp.json`；Reasonix 全局范围可用 `--write` 追加 `[[plugins]]` 到 `config.toml`，写入前自动备份，同名插件已存在时拒绝重复写入。详见 [mcp.md](mcp.md)。
- `register.py` 覆盖 claude / codex / reasonix / generic 四个宿主。**opencode 的 MCP 配置格式未在本包中实测**，调用会返回明确错误而不是生成未验证的配置；Skill 安装不受影响。
- 宿主集合与路径由 `tools/check_hosts.py` 在回归测试中校验，三处脚本与本文档必须一致。
- A2A 客户端与服务端由 `scripts/nucleara2a.py` 提供；协议、策略与特批规则见 [a2a.md](a2a.md)，威胁模型见 [threat-model.md](threat-model.md)。
- 两者都调用同一个 `nuclearlib.py`，不得为宿主复制或弱化门禁规则。

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
