# nuclear-dev-kit 安装与部署教程

本教程面向在**另一台电脑**上部署 `nuclear-dev-kit` 的操作者。按顺序执行即可；每一步都给出了预期结果，出现不符时先停下排查，不要跳过。

> 工程边界：本包不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

---

## 0. 包里有什么

解压后应有：

```text
INSTALL.md                 本教程
SHA256SUMS.txt             所有文件的 SHA-256，用于校验传输完整性
nuclear-dev-kit/
  README.md
  reasonix-plugin.json           Reasonix 插件清单
  .claude-plugin/                Claude Code 插件清单
  .codex-plugin/                 Codex 插件清单
  skills/
    nuclear-dev/                 总入口 + 冻结门禁 + MCP/A2A 适配层
      references/                workflow / artifact-schema / mcp / a2a / threat-model
      scripts/
        nuclearlib.py            唯一门禁实现（不要修改）
        nuclearctl.py            门禁 CLI
        nuclearmcp.py            MCP stdio 服务端
        nucleara2a.py            A2A 客户端与服务端
        nuclearaudit.py          审计链查看与校验
        nuclearproto/            协议适配层
    nuclear-setup/               初始化与底层安装器
    nuclear-install/             便捷安装入口 + MCP 注册片段生成
    nuclear-plan/                阶段 1 软件策划
    nuclear-requirements/        阶段 2 需求分析
    nuclear-design/              阶段 3 软件设计
    nuclear-implementation/      阶段 4 编码实现
    nuclear-test/                阶段 5 软件测试
    nuclear-vv/                  阶段 6 独立 V&V
    nuclear-release/             阶段 7 软件发布
  tests/                         回归测试（211 项）
  tools/build_dist.py            可复现打包
```

十个 Skill 中，`nuclear-dev/scripts/nuclearlib.py` 是门禁规则的**唯一事实来源**，所有阶段、所有宿主、MCP 与 A2A 都调用它。不要复制、改写或"裁剪"它。

包提供三个面：Skill（工程指令）、MCP（确定性判定与受控写入）、A2A（远程 V&V）。三个面共用同一内核，判定必须一致。

---

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| Python | 3.7.3 或更高；只用标准库，无需 pip install |
| 网络 | 不需要。整套流程可完全离线运行 |
| 磁盘 | 约 1 MB（压缩包约 200 KB） |
| 操作系统 | Windows / Linux / macOS 均可 |
| 宿主（可选） | Claude Code、Codex、opencode、Reasonix，或任何能读文件、能执行命令的 Agent |

### 1.1 确认 Python

Linux / macOS / Git Bash：

```bash
python3 --version
```

Windows PowerShell 或 cmd：

```powershell
py -3 --version
```

应输出 `Python 3.7.3` 或更高。**下文命令统一写 `python3`；在 Windows 上用 `py -3` 替换即可。**

Windows 上如果 `python3` 弹出 Microsoft Store，说明只有商店别名、没有真实解释器。改用 `py -3`，或安装 python.org 的正式版本。

---

## 2. 传输与解压

1. 把 `nuclear-dev-kit-0.1.0.zip` 拷到目标电脑。
2. **先校验完整性**（可选但推荐）：

   Linux / macOS / Git Bash：

   ```bash
   sha256sum -c SHA256SUMS.txt
   ```

   Windows PowerShell：

   ```powershell
   Get-FileHash .\nuclear-dev-kit-0.1.0.zip -Algorithm SHA256
   ```

   对照随包提供的压缩包校验值。校验文件内每行以 `OK` 结尾即为通过；出现 `FAILED` 请重新传输。

3. 解压到一个**路径不含空格和中文**的位置，例如：

   - Windows：`C:\tools\nuclear-dev-kit`
   - Linux / macOS：`~/tools/nuclear-dev-kit`

   解压后应看到 `INSTALL.md`、`SHA256SUMS.txt` 与 `nuclear-dev-kit/` 目录；进入 `nuclear-dev-kit/` 后应看到 `skills/`、`README.md` 与 `tests/`。

> 路径不含空格与中文不是硬性限制，但能避免一部分 shell 引号与编码问题，尤其是 Windows。

---

## 3. 完整性自检（约 30 秒）

**在安装之前**先确认 CLI 能跑：

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --help
```

预期看到子命令：`init`、`status`、`validate`、`gate`、`evidence`、`manifest`，以及阶段顺序 `plan -> requirements -> design -> implementation -> test -> vv -> release`。

再做一次冒烟测试，在临时目录建一个工作区：

```bash
mkdir -p /tmp/nuclear-smoke
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py \
  --root /tmp/nuclear-smoke init --name "冒烟测试" --id smoke-test --json
```

预期 `ok: true`，并生成 `/tmp/nuclear-smoke/.nuclear-dev/`（含 `project.json`、`traceability.json`、`stages/`、`evidence/`、`approvals/`、`manifests/`）。测试完可整个删掉。

> 本包自带回归测试。安装前可以先跑一遍：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests
```

预期全部测试通过（Windows 上跳过 1 项仅 POSIX 可做的权限测试）。若测试失败，先排查 Python 环境，不要继续安装。

---

## 4. 把 Skill 装到宿主（推荐路径）

安装器位于 `<KIT>/skills/nuclear-setup/scripts/install.py`，它只复制十个 Skill 目录，**不写宿主配置、不改项目源码、不生成批准文件**。便捷入口 `<KIT>/skills/nuclear-install/scripts/quickinstall.py` 在此基础上增加宿主自动检测、初始化与验证编排。

### 4.0 一条命令安装（推荐）

```bash
python3 <KIT>/skills/nuclear-install/scripts/quickinstall.py --json
python3 <KIT>/skills/nuclear-install/scripts/quickinstall.py --yes --json
```

- 默认 `global` 范围，自动检测宿主；未检测到时用 `--host claude|codex|opencode|reasonix|generic|all` 指定。
- 默认 dry-run；只有 `--yes` 才写入。目标已存在时同样需要 `--force`。
- 需要同时初始化工作区并验证：加 `--init --verify`，用 `--project` 指定项目根目录。
- 下方 4.1–4.4 是等价的手动分步流程，排查问题时可逐步执行。

### 4.1 选宿主与范围

| 宿主 | `--scope project` 目标 | `--scope global` 目标 |
|---|---|---|
| `claude` | `<项目>/.claude/skills` | `~/.claude/skills` |
| `codex` | `<项目>/.agents/skills` | `$CODEX_HOME/skills` 或 `~/.codex/skills` |
| `opencode` | `<项目>/.opencode/skills` | `~/.config/opencode/skills` |
| `reasonix` | `<项目>/.reasonix/skills` | `$REASONIX_HOME/skills`；Windows `%APPDATA%\reasonix\skills`；其他 `~/.reasonix/skills` |
| `generic` | `<项目>/.agents/skills` | `~/.agents/skills` |
| `all` | 以上全部，按绝对路径去重 | 同上 |

- **项目级**：只在该项目里生效，适合一个项目一套流程。
- **全局**：这台机器上所有项目都能用，适合经常新建核能软件项目的人。
- `all` 会把 `codex` 与 `generic` 都指向 `.agents/skills`，安装器按绝对路径去重，不会重复写。

### 4.2 先 dry-run

在**你要安装的项目根目录**执行（以 Claude Code 项目级为例）：

```bash
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude \
  --scope project --project "$PWD" --json
```

Windows PowerShell：

```powershell
py -3 "$env:KIT\skills\nuclear-setup\scripts\install.py" claude `
  --scope project --project "C:\work\my-nuclear-proj" --json
```

预期 `"dry_run": true`、`"status": "planned"`，并在 `targets` 里列出 10 个目标路径。**这一步不写任何文件。**

检查三件事：目标路径是否是你想要的、`conflicts` 是否为空、10 个 Skill 是否齐全。

### 4.3 确认后写入

```bash
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude \
  --scope project --project "$PWD" --yes --json
```

预期 `"ok": true`、`"status": "installed"`、`"dry_run": false`，退出码 `0`。

安装到全部宿主（项目级）：

```bash
python3 <KIT>/skills/nuclear-setup/scripts/install.py all \
  --scope project --project "$PWD" --yes --json
```

安装到本机全局（Claude Code、Reasonix 等）：

```bash
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude --scope global --yes --json
python3 <KIT>/skills/nuclear-setup/scripts/install.py reasonix --scope global --yes --json
```

> **装完即可移动或删除整个 `nuclear-dev-kit/` 目录。** 安装器复制的是完整 Skill 目录（含 `scripts/`），宿主里的副本是自包含的。若要保留安装器以便日后升级，则保留原包。

### 4.4 覆盖已有安装

目标已存在时安装器默认**拒绝**：`"status": "conflict"`，退出码 `1`，`conflicts` 列出每一项。

确认要覆盖时加 `--force`：

```bash
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude \
  --scope project --project "$PWD" --yes --force --json
```

覆盖前会在目标 Skill 根目录的 `.nuclear-dev-kit-backups/<UTC 时间戳>/` 下自动备份，`backups` 字段会给出路径。回滚时把备份目录里的内容拷回即可。

### 4.5 可选：注册 MCP 面

Skill 只提供工程指令。要让宿主通过确定性工具调用门禁，再注册 MCP 服务端：

```bash
R=<KIT>/skills/nuclear-install/scripts/register.py

# 只打印片段，不写配置
python3 "$R" claude --scope project --project "$PWD" --json

# 确认后合并写入项目级 .mcp.json（写入前备份）
python3 "$R" claude --scope project --project "$PWD" --write --json

# 需要写入工具时
python3 "$R" claude --scope project --project "$PWD" --allow-write --json
```

- 默认只读；写入工具必须显式 `--allow-write`。
- Codex 输出 TOML 片段，由你手工追加到 `config.toml`；本工具不为 Codex 写 TOML。
- Reasonix 原生读取项目根 `.mcp.json`，项目级可直接 `--write`；全局范围可加 `--write` 自动追加 `[[plugins]]` 到 `%APPDATA%\reasonix\config.toml`（Windows）或 `~/.reasonix/config.toml`，写入前备份，同名插件已存在时拒绝重复写入。写入后还需在项目里执行一次 `reasonix mcp enable nuclear-dev`——仓库声明的 server 默认关闭，启用后进程在首次工具调用时启动。
- 注册后在新会话里确认 `tools/list` 返回 6 个只读工具，且不存在任何 `approve` 工具。

A2A 面（远程 V&V）默认不启用：需要显式写导出策略、生成一次性令牌并配置对端，见 `skills/nuclear-dev/references/a2a.md`。

---

## 5. 初始化业务项目的工作区

Skill 装好后，还要在**每个**受控项目里初始化门禁工作区。

```bash
cd /path/to/my-nuclear-proj
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py \
  --root . init --name "示例核能软件" --id example-nuclear --json
```

`--id` 用小写字母、数字和连字符。

预期 `ok: true`，并生成：

```text
.nuclear-dev/
  project.json          项目元数据（名称、ID、schema 版本，安全分级与 V&V 等级初始为 pending）
  traceability.json     追溯关系（初始为空）
  stages/{plan,requirements,design,implementation,test,vv,release}/
  evidence/index.json   证据索引
  approvals/            人工批准（本工具永不写入）
  manifests/            发布清单
```

**只建结构，不建阶段产物。** 已初始化过的项目不要重复 `init`，用 `status` / `validate` 检查即可。

若已把 Skill 装进宿主，也可以不手敲这条命令，直接让 Agent 使用 `nuclear-setup` Skill 完成初始化（或使用 `nuclear-install` 的 `--init`）。

---

## 6. 验证安装

### 6.1 命令行验证

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --root . status --json
```

预期列出七个阶段，每项带当前状态。`status` 不递归检查前置阶段，**始终返回退出码 `0`**。

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --root . gate plan --json
```

全新项目这里应当**失败并返回 `1`**——这是正确行为：`plan` 阶段尚无产物。它同时证明门禁在工作。

### 6.2 宿主内验证

打开**新会话**（让宿主重新扫描 Skill 目录），然后：

| 宿主 | 调用方式 |
|---|---|
| Claude Code | `/nuclear-plan`（插件安装时可能带命名空间），或在 Skill 列表中选择 |
| Codex | `$nuclear-plan`，或在技能列表中选择 |
| opencode | `/nuclear-plan` 或宿主提供的 Skill 选择器 |
| Reasonix | 在 Skill 入口选择，或自然语言点名"使用 nuclear-plan" |
| 通用 Agent | 直接读取 `skills/nuclear-plan/SKILL.md` |

确认十项齐全：`nuclear-dev`、`nuclear-setup`、`nuclear-install`、`nuclear-plan`、`nuclear-requirements`、`nuclear-design`、`nuclear-implementation`、`nuclear-test`、`nuclear-vv`、`nuclear-release`。

进入 `nuclear-plan` 后，第一件事应是只读检查（`status --json` 与 `gate plan --json`），而不是直接写文件。若 Agent 跳过检查直接产出内容，说明 Skill 未被正确加载。

### 6.3 可选：MCP 与 A2A 自检

MCP：

```bash
# 直接启动 stdio 服务端；等待 JSON-RPC 输入，Ctrl-C 退出
python3 <KIT>/skills/nuclear-dev/scripts/nuclearmcp.py --workspace "$PWD"
```

启动信息只写 stderr；stdout 只应出现 JSON-RPC 消息。

审计链：

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nuclearaudit.py --root . verify --json
```

A2A（V&V 方）：

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nucleara2a.py --project "$PWD" policy-template
python3 <KIT>/skills/nuclear-dev/scripts/nucleara2a.py --project "$PWD" serve \
  --organization "V&V 组织" --spec-revision <锁定修订> --keys <keys.json> \
  --transfer-root /path/to/exchange
```

服务端默认只绑定 loopback；非 loopback 必须直连 TLS。详见 `skills/nuclear-dev/references/a2a.md`。

Reasonix 的 MCP 启动验证：

```bash
reasonix mcp list
reasonix mcp enable nuclear-dev          # 仓库声明的 server 默认关闭，需显式启用
reasonix doctor capabilities --live --json
```

预期 `mcp list` 出现 `nuclear-dev (stdio)`；live 结果中 `runtime_status=probed`、`tool_count=6`。

---

## 7. 手动安装（没有 Python 或不想用安装器时）

安装器的动作很简单：把 `nuclear-dev-kit/skills/` 下的**十个目录**复制到宿主的 skills 目录。

```bash
# 以 Claude Code 项目级为例
mkdir -p /path/to/proj/.claude/skills
cp -r <KIT>/skills/nuclear-dev* /path/to/proj/.claude/skills/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:PROJ\.claude\skills"
Copy-Item "$env:KIT\skills\nuclear-*" "$env:PROJ\.claude\skills\" -Recurse
```

注意：

- **不要复制整个 `skills/` 目录**，只复制里面的十个 `nuclear-*` 子目录。
- 排除 `__pycache__/` 与 `*.pyc`。
- 没有 Python 时，`nuclearctl.py` 无法运行，门禁也就无法执行。此时必须在报告中明确写"无法执行门禁"，**不得把静态文件说成门禁通过**。

---

## 8. 日常使用

### 8.1 阶段顺序（固定，不可跳）

```text
plan -> requirements -> design -> implementation -> test -> vv -> release
```

| 阶段 | Skill | 主要产物 |
|---|---|---|
| 软件策划 | `nuclear-plan` | `.nuclear-dev/stages/plan/plan.json` |
| 需求分析 | `nuclear-requirements` | `.nuclear-dev/stages/requirements/requirements.json` |
| 软件设计 | `nuclear-design` | `.nuclear-dev/stages/design/design.json` |
| 编码实现 | `nuclear-implementation` | `.nuclear-dev/stages/implementation/implementation.json` |
| 软件测试 | `nuclear-test` | `.nuclear-dev/stages/test/test-report.json` |
| 独立 V&V | `nuclear-vv` | `.nuclear-dev/stages/vv/vv-report.json` |
| 软件发布 | `nuclear-release` | `.nuclear-dev/stages/release/release.json` |

### 8.2 每个阶段的固定循环

1. **检查**：`status --json` + 目标阶段递归 `gate --json`，记录真实错误。
2. **读取**：已有 JSON 就读进来保留原字段，绝不空模板覆盖；不存在则按 `skills/nuclear-dev/references/artifact-schema.md` 起草。
3. **起草**：需求、假设、适用范围、限制、验证方法写清楚；未知项进 `open_items`。
4. **执行**：做真实的工程活动（构建、跑测试、基准算例、误差分析），保留原始记录。
5. **登记证据**：见 8.3。
6. **追溯**：更新 `.nuclear-dev/traceability.json` 的 `nodes` 与 `links`，双向语义一致。
7. **复核**：`validate --json`，再跑目标阶段递归 `gate --json`。
8. **停止或交接**：需要人工批准的阶段，产物稳定后停下，列清待批准产物及其 SHA-256，交真人独立签署。

### 8.3 登记证据

证据文件必须位于**项目目录内**，且同一路径不能重复登记。

```bash
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --root . \
  evidence add ./reports/unit-test.log \
  --kind test --producer "张工" \
  --command "ctest -R solver" --result passed --json
```

- `evidence.id` **只能**从返回 JSON 的 `evidence.id` 字段读取（形如 `EVID-xxx`），不要自己编号。
- `--result` 只填实际结果：`passed` / `failed` / `observed` / `not_applicable`。失败的证据是有价值的诊断记录，不要改成 `passed`。
- 证据内容变化后哈希会不匹配，必须按真实结果重新登记新文件；不能手改索引里的 SHA。

### 8.4 退出码

| 码 | 含义 | 怎么办 |
|---|---|---|
| `0` | 通过（或 `status`/dry-run 正常结束） | 继续 |
| `1` | 门禁失败、校验失败、安装冲突 | 看 JSON 里的真实阻断项；不要弱化规则绕过 |
| `2` | 参数或工具错误 | 修正调用方式，**不要**当成"阶段未完成" |

---

## 9. 不可越过的边界

- **不存在 `approve` 子命令。** `.nuclear-dev/approvals/*.json` 必须由具备权限的真实人员独立创建、审查并签署。Agent 不得生成、修改或推断这些文件。阶段产物一旦变化，旧批准自动失效。
- `TBD`、`TODO`、`UNKNOWN`、`DRAFT` 等占位值会被门禁阻断。未知项写进 `open_items`，只有 `closed` 状态才解除阻断。
- 门禁失败就停在该阶段，如实报告阻断项。不得修改 `nuclearlib.py`、伪造测试结果或宣称合规。
- 无法执行命令时，明确报告限制，不得把静态文件说成门禁通过。

---

## 10. 常见问题

**Q：`python3` 命令不存在 / 打开应用商店。**
Windows 上用 `py -3` 替代；或安装 python.org 正式版并勾选 "Add Python to PATH"。

**Q：命令报 `--root` 相关参数错误（退出码 2）。**
`--root` 必须放在子命令**之前**：

```bash
# 对
nuclearctl.py --root . gate plan --json
# 错
nuclearctl.py gate plan --root . --json
```

**Q：控制台中文变成乱码。**
设置 UTF-8 输出：

```bash
export PYTHONIOENCODING=utf-8          # Git Bash / Linux / macOS
```

```powershell
$env:PYTHONIOENCODING = "utf-8"        # PowerShell
chcp 65001                             # cmd
```

**Q：安装返回 `status: conflict`、退出码 1。**
目标已存在。确认要覆盖时加 `--force`（会先备份到 `.nuclear-dev-kit-backups/<时间戳>/`）；或先手动删除对应的十个 Skill 目录。

**Q：安装到项目级，但宿主里看不到 Skill。**
项目级目录必须位于宿主的**项目根目录**。确认 `--project` 指向的是打开的那个项目；重启宿主或新开会话让 Skill 目录重新扫描。

**Q：`gate plan` 直接失败。**
全新项目这是正常的——`plan` 还没有产物。先完成该阶段并按 Schema 产出 `plan.json`。

**Q：能不能只把 `skills/` 拷到别处用？**
可以，`skills/` 是自包含的。但必须保留每个 Skill 内的 `scripts/`，因为门禁靠它执行。任何时候都要调用同一份 `nuclearlib.py`。

**Q：升级到新版本怎么做？**
用新包再跑一次安装器，加 `--yes --force`；备份目录会保留旧版本。项目里的 `.nuclear-dev/` 数据不受影响，升级后跑一次 `validate --json` 确认 Schema 兼容。

**Q：怎么卸载？**
删除宿主 skills 目录下的十个 `nuclear-*` 目录即可。项目里的 `.nuclear-dev/` 是业务数据，按其自身配置管理策略处理，别和 Skill 一起删。

**Q：能联网吗 / 需要装依赖吗？**
不需要网络，也不需要任何第三方包。全部是 Python 标准库。

---

## 11. 附：一键复制清单

把 `<KIT>` 换成实际路径后逐条执行。

```bash
# 0) 便捷路径：自动检测宿主，预览 → 安装 → 初始化 → 验证
python3 <KIT>/skills/nuclear-install/scripts/quickinstall.py --json
python3 <KIT>/skills/nuclear-install/scripts/quickinstall.py --yes --json

# 1) 自检
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --help

# 2) 预览安装（Claude Code，项目级）
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude \
  --scope project --project "$PWD" --json

# 3) 确认安装
python3 <KIT>/skills/nuclear-setup/scripts/install.py claude \
  --scope project --project "$PWD" --yes --json

# 4) 初始化门禁工作区
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py \
  --root . init --name "项目名称" --id project-id --json

# 5) 查看状态并进入第一阶段
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --root . status --json
python3 <KIT>/skills/nuclear-dev/scripts/nuclearctl.py --root . gate plan --json

# 6) 回归测试（可选）
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests

# 7) MCP 注册片段（可选，默认只打印）
python3 <KIT>/skills/nuclear-install/scripts/register.py claude \
  --scope project --project "$PWD" --json

# 8) 审计链校验（可选）
python3 <KIT>/skills/nuclear-dev/scripts/nuclearaudit.py --root . verify --json
```

完成以上步骤即可开始第一阶段。后续阶段由对应 Skill 引导，规则见 `skills/nuclear-dev/references/workflow.md`。

> 安装/升级时优先使用 `nuclear-install`：它把宿主检测、预览、写入、初始化和验证串成一条命令，规则与 `nuclear-setup` 的底层安装器完全一致。
