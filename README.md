# nuclear-dev-kit：核能软件七阶段研发能力与 nuclear-dev-agent 智能体

`nuclear-dev-kit` 把核能数值软件的七阶段研发流程封装为可移植的 Agent Skill 包。它面向核工程、科学计算和受控软件研发场景，提供统一的阶段产物 Schema、证据登记、需求-设计-实现-测试-V&V 追溯，以及逐阶段人工批准停止点。

仓库由两部分组成：

- `skills/`：十个 `nuclear-*` Skill 与唯一门禁实现 `nuclearlib.py`，可装进 Claude Code、Codex、opencode、Reasonix、DeepSeek Harness 或任意 Agent；
- [`nuclear-dev-agent/`](nuclear-dev-agent/)：仓库主体，一个 DeepSeek Harness bundle（由 `superagent` 原型改造，来源见 [FORK.md](nuclear-dev-agent/FORK.md)），把七阶段装进「接活 → 开 Ticket → 独立 Session 执行 → 回帖」的链路，并带网页面板；一条命令部署见下文「智能体」一节。

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

## 适合什么时候使用

- 新建或维护核能数值求解器、物理模型、材料/物性库及其测试体系。
- 需要把物理需求、数值方法、代码实现、测试证据和 V&V 结论串成一条可审计链路。
- 需要在 Claude Code、Codex、opencode、Reasonix、DeepSeek Harness 或通用 Agent 中复用同一套门禁与工作流。
- 想让智能体自己接活、按七阶段推进，并在网页面板上看到每个工作区的阶段板：用 `nuclear-dev-agent`。

本包不是质量保证体系的认证，也不替代适用法规、标准、持证人员判断或真实工程测试。无法执行命令时，Agent 必须明确报告限制，不能把静态文件说成门禁通过。

## 七阶段

| 阶段 | Skill | 主要产物 |
|---|---|---|
| 软件策划 | `nuclear-plan` | `.nuclear-dev/stages/plan/plan.json` |
| 需求分析 | `nuclear-requirements` | `.nuclear-dev/stages/requirements/requirements.json` |
| 软件设计 | `nuclear-design` | `.nuclear-dev/stages/design/design.json` |
| 编码实现 | `nuclear-implementation` | `.nuclear-dev/stages/implementation/implementation.json` |
| 软件测试 | `nuclear-test` | `.nuclear-dev/stages/test/test-report.json` |
| 独立 V&V | `nuclear-vv` | `.nuclear-dev/stages/vv/vv-report.json` |
| 软件发布 | `nuclear-release` | `.nuclear-dev/stages/release/release.json` |

总入口是 `nuclear-dev`；首次安装、升级和多宿主部署用 `nuclear-install`（自动检测宿主、预览后写入），工作区初始化与底层安装器由 `nuclear-setup` 负责。每个阶段 Skill 都先运行只读检查和递归门禁，再开展真实工程活动；阶段产物变化后，旧的人工批准会自动失效。

## 快速开始

要求 Python 3.7.3 或更高版本，仅使用标准库。

### 一条命令安装（推荐）

```bash
# 自动检测宿主，预览安装计划（不写文件）
python3 nuclear-dev-kit/skills/nuclear-install/scripts/quickinstall.py --json

# 用户确认后写入
python3 nuclear-dev-kit/skills/nuclear-install/scripts/quickinstall.py --yes --json

# 装到指定项目并初始化工作区、执行真实检查
python3 nuclear-dev-kit/skills/nuclear-install/scripts/quickinstall.py claude \
  --scope project --project /path/to/project --init --verify --yes --json
```

`quickinstall.py` 默认 `global` 范围与 dry-run；只有 `--yes` 才写入。目标已存在时默认拒绝，`--force` 会先备份。

### 分步执行

```bash
# 1. 初始化项目门禁工作区
python3 nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py \
  --root /path/to/project init --name "示例核能软件" --id example-nuclear --json

# 2. 查看状态并进入第一阶段
python3 nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py \
  --root /path/to/project gate plan --json

# 3. 预览安装到 Codex 项目级 Skill 目录
python3 nuclear-dev-kit/skills/nuclear-setup/scripts/install.py codex \
  --scope project --project /path/to/project --json

# 4. 用户确认后写入
python3 nuclear-dev-kit/skills/nuclear-setup/scripts/install.py codex \
  --scope project --project /path/to/project --yes --json
```

安装器默认 dry-run。只有同时提供 `--yes` 且未显式使用 `--dry-run` 时才写入；已存在的目标默认作为冲突拒绝，使用 `--force` 时先创建 UTC 时间戳备份。

## MCP 面（可选）

Skill 负责工程指令，MCP 负责确定性判定。注册后，支持 MCP 的宿主可直接调用 `nuclear_status`、`nuclear_gate`、`nuclear_validate`、`nuclear_read_artifact`、`nuclear_schema`、`nuclear_evidence_list`；只有加 `--allow-write` 才暴露 `nuclear_init`、`nuclear_evidence_add`、`nuclear_manifest`。任何模式都不提供批准工具。

```bash
# 生成注册片段：默认只打印，不写宿主配置
python3 nuclear-dev-kit/skills/nuclear-install/scripts/register.py claude \
  --scope project --project /path/to/project --json

# 用户确认后合并写入项目级 .mcp.json（写入前备份）
python3 nuclear-dev-kit/skills/nuclear-install/scripts/register.py claude \
  --scope project --project /path/to/project --write --json
```

服务端契约见 [skills/nuclear-dev/references/mcp.md](skills/nuclear-dev/references/mcp.md)。Reasonix 原生读取项目根 `.mcp.json`，项目级注册与 Claude Code 相同；写入后需执行一次 `reasonix mcp enable nuclear-dev`。全局范围可加 `--write` 自动追加 `[[plugins]]` 到 `%APPDATA%\reasonix\config.toml`（Windows）或 `~/.reasonix/config.toml`，写入前自动备份，同名插件已存在时拒绝重复写入。`register.py` 覆盖 claude / codex / reasonix / generic / dsh；opencode 的 MCP 配置格式未实测，调用会返回明确错误，Skill 安装不受影响。

## DeepSeek Harness (DSH) 支持

本项目可作为 DeepSeek Harness bundle 部署。想尽快跑起来，直接用一条命令（见下节「智能体」）：

```bash
python3 tools/deploy_nuclear_dev_agent.py         # 预览
python3 tools/deploy_nuclear_dev_agent.py --yes   # 执行：构建 agent、装 Skill、建 profile、写配置
```

手工装配时分三层，按需取用：

1. **Skill 层（必装）**：`install.py` / `quickinstall.py` 支持 `dsh` 宿主，项目级装到 `<项目>/.dsh/skills`，全局装到 `$DSH_HOME/skills`（或 `~/.dsh/skills`）。这两个目录是 DSH 内置 `@deepseek-ai/dsh-skill-filesystem` 的扫描根，装完新开会话即可看到十个 `nuclear-*` Skill。

   ```bash
   python3 nuclear-dev-kit/skills/nuclear-setup/scripts/install.py dsh \
     --scope project --project /path/to/project --yes --json
   ```

2. **MCP 层（可选）**：根目录 `package.json` 声明 `dsh.bundle.patch` → `cordis.patch.yml`，用 `@deepseek-ai/dsh-mcp-client` 把 `nuclear-dev` 门禁桥接为 `mcp__nuclear-dev__*` 工具。bundle 会被 link 到任意 profile，patch 里无法写死绝对路径，因此该行默认关闭，设置环境变量后启用：

   ```bash
   export NUCLEAR_DEV_MCP_SERVER=/path/to/nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearmcp.py
   export NUCLEAR_DEV_MCP_PYTHON=python3        # 可选，默认 python3
   export NUCLEAR_DEV_MCP_WORKSPACE=/my/project # 可选，单个被门禁管理的工作区
   ```

   或者直接生成带绝对路径的片段，追加到 profile 的 `cordis.patch.yml`，或用 `dsh --patch` 挂载：

   ```bash
   python3 nuclear-dev-kit/skills/nuclear-install/scripts/register.py dsh \
     --scope project --project /path/to/project --json
   ```

3. **Bundle 挂载**：`dsh plugin --profile <profile> add link:<本仓库路径>`，并把 `nuclear-dev-kit` 加进该 profile `package.json` 的 `dsh.profile.bundles`。

默认 patch 只暴露只读工具，`--allow-write` 仍需显式添加；任何形态都不提供批准工具。

## 智能体：nuclear-dev-agent（核能软件开发全流程）

[`nuclear-dev-agent/`](nuclear-dev-agent/) 是本仓库的主体：一个 DSH（DeepSeek Harness）bundle，
把本包的七阶段门禁装进「主动接活 → 开 Ticket → 独立 Session 执行 → 回帖」这条链路，让智能体按
`nuclear-plan` → … → `nuclear-release` 干活。它以 `superagent` 原型为骨架改造而来，来源与逐项改动见
[`nuclear-dev-agent/FORK.md`](nuclear-dev-agent/FORK.md)。

分工：一个**总控智能体**（主 Session）与七个**阶段智能体**。总控只决定「这个请求是哪个阶段」并把工单交给
该阶段的智能体；七个阶段智能体（策划、需求、设计、实现、测试、独立 V&V、发布）各拥有一个阶段、一份产物、
一个 Skill 和它的门禁。一个工单一次由一个阶段智能体做，门禁接受该阶段后由宿主交给下一个；产物没过门禁就不
推进，签名仍然只能由人签。设计与边界见 [nuclear-dev-agent/docs/010-stage-agents.md](nuclear-dev-agent/docs/010-stage-agents.md)。

```bash
python3 tools/deploy_nuclear_dev_agent.py          # 预览：构建 agent、装 Skill、建 profile、写配置
python3 tools/deploy_nuclear_dev_agent.py --yes    # 一条命令部署完
dsh nuclear-dev-agent                              # 起来用（面板 http://127.0.0.1:3082）
```

部署脚本把十个 `nuclear-*` Skill 装到 `$DSH_HOME/skills`（DSH 用户级 Skill 根，所有 profile 与 Ticket
工作目录都看得到），把两个 bundle 链接进 profile 并补上 `dsh.profile.bundles`，写好面板端口与 `stateDir`，
并把本仓库的绝对路径写成 agent 的 `nuclear.kitPath`，最后用 `dsh --dump-config` 复核。重复执行安全：
Skill 已装齐就跳过，配置行已在位就不重写。

核能流程在 agent 内部的位置：

| 部分 | 做什么 |
|---|---|
| `src/nuclear/` | 七阶段表，以及 `nuclearctl.py` 的桥接：`status` 读每个阶段，`gate <阶段>` 读当前阶段的递归门禁；门禁消息逐字照抄 |
| `src/app/nuclear.ts` | 按工单目录缓存扫描、解释器探测，向面板与概览提供阶段板 |
| `prompts/nuclear.md` | 两个角色的内置段落 `runtime/nuclear`：阶段、命令、以及「批准只能由人签、门禁失败即停」 |
| `src/nuclear/agents.ts` | 总控智能体与七个阶段智能体的表：名字、Skill、产物与一句话职责 |
| `prompts/chief.md` / `prompts/stage/<阶段>.md` | 总控的派活规则（`runtime/chief`），以及每个阶段智能体自己那一段（`runtime/stage/<阶段>`）；团队可在面板改写 |
| 面板「核能流程」 | 每个工作区一块七阶段板；工单页带本工单的阶段段；概览列出被门禁停住的阶段 |
| `DSH_NUCLEAR_DEV_AGENT_KIT` / `..._NUCLEARCTL` | 执行环境变量：本机 kit 目录与门禁命令行，主 Session 与执行器都能直接调用 |

它不生成批准、不放宽门禁：阶段过不过只由 `nuclearlib.py` 判定，面板只转述它的原话。
参数、环境变量与限制见 [docs/nuclear-dev-agent.md](docs/nuclear-dev-agent.md)。

## A2A 面（远程 V&V）

独立 V&V 由外部组织开展时，用 `nucleara2a.py` 生成投影包并委托。客户端与服务端均已实现。

```bash
A=nuclear-dev-kit/skills/nuclear-dev/scripts/nucleara2a.py

# 1) 生成投影包（只写本地 outbox，不外发）
python3 "$A" --project /path/to/project --json plan --recipient vv-org

# 2) 在终端里生成一次性令牌（需要交互终端）
python3 "$A" --project /path/to/project authorize \
  --bundle <投影包目录> --approver <姓名> --ttl 15m

# 3) 暂存到带外交换目录，然后发送
python3 "$A" --project /path/to/project stage \
  --config <a2a-config.json> --keys <keys.json> --recipient vv-org --bundle <目录>
python3 "$A" --project /path/to/project send \
  --config <a2a-config.json> --keys <keys.json> --recipient vv-org \
  --bundle <目录> --token AUTH-...
```

外发默认拒绝：必须先写 `.nuclear-dev/a2a/export-policy.json`。C3 原始文件需要双人 EXP 特批，且只能从 CLI 发送。协议画像、策略、特批与令牌格式见 [skills/nuclear-dev/references/a2a.md](skills/nuclear-dev/references/a2a.md)，威胁模型见 [skills/nuclear-dev/references/threat-model.md](skills/nuclear-dev/references/threat-model.md)。本项目实现的是自有画像 `nuclear-a2a/1`，**不是 A2A 规范的一致性实现**，与上游规范的逐节对照见 [a2a-coverage.md](skills/nuclear-dev/references/a2a-coverage.md)。

V&V 方启动服务端：

```bash
python3 "$A" --project /path/to/vv-project serve \
  --organization "V&V 组织" --spec-revision <锁定修订> --keys <keys.json> \
  --transfer-root /mnt/vv-exchange
```

服务端默认只绑定 loopback；非 loopback 必须直连 TLS 或由反向代理终止。任务账本用 `task list` / `task show` / `task update` / `task artifact` 管理。

## 命令与事实来源

`--root` 必须放在子命令之前：

```bash
python3 nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py --root <项目> gate <阶段> --json
python3 nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

- `status` 只检查各阶段当前产物，不递归检查依赖，始终返回 `0`。
- `gate` 默认递归检查前置阶段；门禁失败返回 `1`，参数或工具错误返回 `2`。
- `validate` 校验已存在产物、证据哈希、追溯和已登记批准。
- 证据 ID 只能从 CLI JSON 的 `evidence.id` 获取；同一路径不能重复登记。
- 不存在 `approve` 子命令。批准文件必须由具备权限的真实人员独立创建、审查和签署。

## 安装目标

| 宿主 | 项目级 | 全局 |
|---|---|---|
| Claude Code | `.claude/skills` | `~/.claude/skills` |
| Codex | `.agents/skills` | `$CODEX_HOME/skills` 或 `~/.codex/skills` |
| opencode | `.opencode/skills` | `~/.config/opencode/skills` |
| Reasonix | `.reasonix/skills` | `$REASONIX_HOME/skills`；Windows `%APPDATA%\reasonix\skills`；其他 `~/.reasonix/skills` |
| DSH（DeepSeek Harness） | `.dsh/skills` | `$DSH_HOME/skills` 或 `~/.dsh/skills` |
| generic | `.agents/skills` | `~/.agents/skills` |

`all` 会安装到所有目标，也按绝对路径去重。安装器只替换十个 Skill 子目录，不替换整个 `skills/`，并排除 `__pycache__` 与 `*.pyc`。

## 包结构

```text
nuclear-dev-kit/
  README.md
  INSTALL.md
  package.json               # DSH bundle 声明：dsh.bundle.patch → cordis.patch.yml
  cordis.patch.yml           # kit 的 MCP 桥接层（默认关闭；部署脚本会写入带绝对路径的一行）
  catalog.json               # 由 tools/gen_catalog.py 生成，勿手改
  reasonix-plugin.json
  .claude-plugin/
    plugin.json
    marketplace.json
  .codex-plugin/
    plugin.json
  skills/
    nuclear-dev/             # 总入口、共享 Schema、冻结内核、MCP/A2A 适配层
      references/            # workflow / artifact-schema / mcp / a2a / threat-model
      scripts/
        nuclearlib.py        # 唯一门禁实现
        nuclearctl.py        # 门禁 CLI
        nuclearmcp.py        # MCP stdio 服务端
        nucleara2a.py        # A2A 客户端与服务端
        nuclearaudit.py      # 审计链查看与校验
        nuclearproto/        # 协议适配层
    nuclear-setup/           # 初始化与底层安装器
    nuclear-install/         # 便捷安装入口 + MCP 注册片段生成
    nuclear-plan/ ... nuclear-release/
  tests/                     # 回归测试
  tools/
    build_dist.py            # 可复现打包
    gen_catalog.py           # 生成并校验 catalog.json
    check_docs.py            # 校验文档与内核一致
    check_hosts.py           # 校验各宿主安装目标
    check_reasonix_deploy.py # 校验 Reasonix 部署片段
    check_nuclear_dev_agent.py # 校验 agent 包的身份、核能模块与来源记录
    deploy_nuclear_dev_agent.py      # 一条命令部署「核能门禁 + nuclear-dev-agent」
  nuclear-dev-agent/                 # 本仓库主体：核能软件开发智能体（来源与改动见 FORK.md）
    FORK.md                          # 上游基点提交与本仓库相对上游的改动清单
    src/nuclear/                     # 七阶段表与 nuclearlib.py 的调用桥接
    src/app/nuclear.ts               # 扫描缓存、工单阶段快照
    src/app/views/nuclear.ts         # 面板与概览的核能视图
    src/client/nuclear.tsx           # 面板「核能流程」页与工单阶段段
    prompts/nuclear.md               # 内置段落 runtime/nuclear
  docs/
    nuclear-dev-agent.md             # 部署、配置与限制说明
```

共享契约只在 `skills/nuclear-dev/references/` 维护。各宿主必须调用同一套 `nuclearlib.py`，禁止复制或弱化门禁规则。

## 验证

```bash
# 在仓库根执行
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v

# 文档、目录、宿主目标与 agent 包身份的一致性
python3 tools/check_docs.py
python3 tools/gen_catalog.py --check
python3 tools/check_hosts.py
python3 tools/check_nuclear_dev_agent.py

find . \( -name '__pycache__' -o -name '*.pyc' \) -print
```

`nuclear-dev-agent/` 的 TypeScript 侧另需 Node 22.19+ 与 pnpm：`cd nuclear-dev-agent && pnpm install && pnpm build`，`pnpm test` 跑 vitest。

测试中的批准只存在于隔离临时目录，是用于验证门禁行为的 fixture，不是真实批准。

## 许可证

MIT。
