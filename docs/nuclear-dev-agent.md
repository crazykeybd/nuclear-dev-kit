# 部署 nuclear-dev-agent：在智能体里跑核能软件开发全流程

[`nuclear-dev-agent/`](../nuclear-dev-agent/) 是本仓库的主体：一个 DeepSeek Harness bundle，
把本包的七阶段门禁装进「主动接活 → 开 Ticket → 独立 Session 执行 → 回帖」这条链路。
**部署只需要一条命令**，不用逐项配 bundle、环境变量或 prepare 命令。

> 工程边界不变：不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 智能体只是执行宿主，不会让门禁变松，也不会产生批准文件。

## 一条命令部署

```bash
python3 tools/deploy_nuclear_dev_agent.py            # 先预览：列出会做什么，不写任何文件
python3 tools/deploy_nuclear_dev_agent.py --yes      # 确认后执行
```

它按顺序做这些事，每步都在 JSON 里留痕：

| 步骤 | 做什么 | 为什么 |
|---|---|---|
| build | 在 `nuclear-dev-agent/` 里 `pnpm install && pnpm build` | 入库的是源码，`lib/` 按包的 `.gitignore` 不入库；缺 Node/pnpm 时预览会标出来，执行阶段直接报错而不装一半 |
| skills | 把十个 `nuclear-*` 装到 `$DSH_HOME/skills` | DSH 的**用户级** Skill 根，所有 profile 与 Ticket 工作目录都能看到 |
| profile | `dsh <profile> --from-default-profile web --dump-config` | profile 不存在时由 DSH 模板创建，已存在则沿用 |
| link | `dsh plugin --profile <profile> add link:<nuclear-dev-agent>`，再 `link:<本仓库>` | 把 agent 与 kit 两个 bundle 链接进 profile |
| bundles | 把 `nuclear-dev-agent`、`nuclear-dev-kit` 补进 `package.json` 的 `dsh.profile.bundles` | 这一步 `dsh plugin` 不管，只能改文件 |
| patch | 写 profile 的 `cordis.patch.yml`：面板端口、`stateDir`、`nuclear.kitPath`（指向本仓库）、`nuclear-dev` 的 MCP 桥接 | 全部用绝对路径，所以不需要任何环境变量 |
| verify | `dsh --profile <profile> --dump-config` 复核这些行确实在组合结果里 | 防止“配置写了但没生效” |

常用参数：

```bash
--profile nuclear-dev-agent   # 目标 profile，默认同名
--port 3082                   # 面板端口
--dsh-home <路径>             # DSH home，默认 $DSH_HOME 或 ~/.dsh
--agent-dir <路径>            # agent 包目录，默认本仓库的 nuclear-dev-agent/
--skip-build                  # 已经构建过时跳过 pnpm（要求 lib/ 存在）
--refresh                     # 即使十个 Skill 已在位也强制重装（安装器会先备份）
--json                        # 机器可读输出
```

默认 dry-run；`--yes` 才写文件。改 `package.json` 与 `cordis.patch.yml` 之前会写
`<文件名>.<UTC 时间戳>.bak` 备份。**已有配置不会被覆盖**：`cordis.patch.yml` 里已有同 id 的行
（比如你自己的 `webserver` 端口、`llm` 供应商）原样保留，缺的那几块追加在文件末尾；预览时
会把「需补什么 / 保留什么」直接打出来。重复执行是安全的：Skill 已装齐就跳过，bundle 与
patch 行已在位就不重写。

部署完还有两件事必须由人来定，脚本不代填：

1. 面板 Sources 里填目标仓库与 agent 账号的 `gh` 包装器，Policy 里填允许名单；
2. 模型供应商若未配置，用面板 Settings 或在 profile 的 `cordis.patch.yml` 里补 `llm` 行。

启动：`dsh nuclear-dev-agent`，面板 `http://127.0.0.1:3082`。

## 智能体里的核能流程

| 部分 | 位置 | 做什么 |
|---|---|---|
| 阶段表 | `nuclear-dev-agent/src/nuclear/types.ts` | 七个阶段的顺序、各自产物与 Skill；阶段状态只有「通过 / 尚无产物 / 等待签署 / 门禁未通过」四种 |
| 门禁桥接 | `nuclear-dev-agent/src/nuclear/scan.ts` | 以子进程跑 `nuclearctl.py --root <工单目录> status` 与 `gate <阶段>` 并解析 JSON；**不复制任何规则**，门禁消息逐字保留 |
| 扫描缓存 | `nuclear-dev-agent/src/app/nuclear.ts` | 每个目录缓存一次扫描（默认 30 秒），面板「重新检查」立即重跑；上限 `nuclear.maxProjects` |
| 管理 API | `GET /orchestrator/api/nuclear`、`POST …/nuclear/refresh`，以及工单详情里的 `nuclear` | 面板数据来源 |
| 提示词 | `nuclear-dev-agent/prompts/nuclear.md` → 内置段落 `runtime/nuclear` | 主 Session 与执行器都读到：阶段、命令，以及不可越界的规则 |
| 阶段智能体表 | `nuclear-dev-agent/src/nuclear/agents.ts` | 总控智能体与七个阶段智能体：名字（中英）、Skill、产物、一句话职责，以及「下一个是谁」 |
| 派活提示词 | `nuclear-dev-agent/prompts/chief.md`、`prompts/stage/<阶段>.md` → `runtime/chief`、`runtime/stage/<阶段>` | 总控怎么选阶段、怎么派；每个阶段智能体自己那一段。团队可在面板改写 |
| 执行环境 | `DSH_NUCLEAR_DEV_AGENT_KIT`、`DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL` | 本机 kit 目录与门禁命令行，prepare 命令和 Session 都用得上 |

三条硬约束写死在提示词里，也由代码结构保证：

- **判定只有一处**：阶段过不过只由 `skills/nuclear-dev/scripts/nuclearlib.py` 说，agent 侧没有任何规则副本；
- **批准只能由人签**：agent 没有任何创建、修改或签署批准的手段，缺批准的阶段在面板上显示为「等待人工批准」；
- **门禁失败即停**：门禁阻断时，执行器报告里带的是门禁原话，工作停在该阶段，不进入下一阶段。

### 总控智能体与七个阶段智能体

一个工单由**一个**阶段智能体做，不是一次做七个：总控智能体（主 Session）接单时用 `orchestrator_route` 的
`stage` 字段指定这个工单是哪个阶段，工单与每次派工都记下这个阶段。产物写完后，执行器报 `ready`，宿主**自己**
用 `nuclearctl.py status` 复查该阶段：门禁不接受，就把门禁原话回给执行器、什么也不记；门禁接受，才把工单交给
下一个阶段智能体（新派工 + 一条 `stage` 输入），最后一个阶段（发布）之后交给人。总控也能用
`orchestrator_route` 的 `kind: stage` 把工单退回某个阶段（比如评审要求改设计）。细节见
[nuclear-dev-agent/docs/010-stage-agents.md](../nuclear-dev-agent/docs/010-stage-agents.md)。

### 部署参数（profile 的 `cordis.patch.yml`）

```yaml
- id: nuclear-dev-agent
  config:
    stateDir: /home/me/.dsh/state/nuclear-dev-agent
    nuclear:
      kitPath: /home/me/src/nuclear-dev-kit   # 本仓库绝对路径；留空表示不接核能流程
      python: python3                          # 跑门禁命令行的解释器
      # timeoutMs: 20000   一次门禁调用的超时
      # maxProjects: 12    一次面板刷新最多扫多少个工单目录
      # refreshSeconds: 30 扫描结果保鲜多久
```

`kitPath` 为空时 agent 照常工作，只是没有核能流程：面板「核能流程」页会说明如何配置。

## 工单目录就是工作树（可选）

每个 Ticket 的目录本来可以由 prepare 命令自己建：默认写法是 `git worktree add`。也可以在面板
**设置 → 执行 → 工作树** 里填上本机 clone 的绝对路径，交给 agent 自己管：

| 设置 | 默认 | 作用 |
|---|---|---|
| 仓库 | 空 | 空表示仍由 prepare 命令建目录；填了就是这张工作树的来源仓库 |
| 目录模板 / 分支模板 | `{name}` / `agent/{name}` | `{name}` 工单短名、`{ticket}` 工单 id、`{repo}` 仓库目录名；目录必须留在执行根目录内 |
| 起始分支 | 空 | 新分支从哪里开始；空表示仓库默认分支（`origin/HEAD`，其次 `origin/main`、`main`、`master`） |
| 结束时清理 | 安全清理 | 工单结束后定期扫一次：分支已并入起始分支、目录没有未提交内容，就移除工作树并（按需）删分支；其余留着并记录原因 |
| 复用已有分支 / 连同分支删除 | 开 / 开 | 目录重建时检出已有分支，工单续做能接上原来的工作 |
| 创建钩子 / 移除钩子 | 空 | 在工作树里用 `sh` 各跑一次，例如装依赖、保存测试产物 |

规则很简单：**有未提交内容的不动，分支还有没并入起始分支的提交也不动；工作树可以收回，分支上的提交不会丢。**
面板「执行」页列出每个工作树的分支、所在工单、未提交数、领先/落后，以及「现在清理」；
主 Session 另有 `orchestrator_worktrees` 工具做同样的事（`list`、`sweep`、`remove`、`prune`）。
细节见 [`nuclear-dev-agent/docs/009-worktrees.md`](../nuclear-dev-agent/docs/009-worktrees.md)。

## 为什么核能 Skill 装在用户级目录

- DSH 的 `@deepseek-ai/dsh-skill-filesystem` 同时扫 `$DSH_HOME/skills`（用户级）与
  `<项目根>/.dsh/skills`（项目级），项目根是「最近的含 `.git` 的祖先」；
- 装到用户级后，agent 的主 Session 与每个 Ticket 的执行器 Session 都直接看得到
  `nuclear-*`，**不需要**改 prepare 命令，也不用来回往工作目录里复制；
- 门禁判定仍然只有 `skills/nuclear-dev/scripts/nuclearlib.py` 一处。

## 验证

1. **部署自检**：`python3 tools/deploy_nuclear_dev_agent.py --json` 里 `verify` 一步的
   `missing_rows` 应为空，`patch.preview` 里应看到 `kitPath` 指向本仓库。
2. **包自检**：`python3 tools/check_nuclear_dev_agent.py --json`（身份、核能模块、来源记录）。
3. **Skill 可见**：`ls "$DSH_HOME/skills"` 应有十个 `nuclear-*`。
4. **面板可读**：打开面板「核能流程」，配置了 kit 时应显示工具包路径与解释器版本；
   工单目录里跑过 `nuclearctl.py init` 之后，该工单页出现「核能七阶段」。
5. **门禁可跑**：在工单目录里跑只读检查：

   ```bash
   python3 /home/me/src/nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py \
     --root "$DSH_NUCLEAR_DEV_AGENT_DIR" status --json
   ```

   全新项目 `gate plan` 返回 `1` 属预期；门禁通过不等于监管批准。
6. **端到端**：让允许列表里的账号在目标仓库的 Issue 上 `@<agent 账号> 用 nuclear-plan 开始第一阶段`。
   约一分钟后 Ticket 出现在面板上，执行器的第一件事应是只读检查而不是直接写文件。

## 已知限制

- **端到端没有在本仓库跑通**：已验证「部署命令把 Skill / bundle / patch / `nuclear.kitPath` 都放对位置」
  「门禁 CLI 在 worktree 上返回真实状态」「`dsh --dump-config` 里这些行确实存在」「agent 的类型检查、
  单元测试与构建通过」「核能桥接对真实 `nuclearlib.py` 的集成测试通过」，没有真的等一个 GitHub Issue
  变成 Ticket 并跑完一个阶段。面板里的 Source / Policy / 模型供应商仍需人配置。
- **需要 Node 工具链**：`nuclear-dev-agent/` 入库的是源码，第一次部署要 `pnpm install && pnpm build`
  （Node.js 22.19+ 或 24+）。没有 Node 的机器只能装 Skill、用不了 agent。
- **一块面板读一份 kit**：`nuclear.kitPath` 是部署级配置；要同时对接两套 kit 版本，就开两个 profile。
- **面板只转述门禁**：阶段状态由门禁输出加两个文件系统事实（产物在不在、批准文件在不在）合成，
  面板不复算任何规则；门禁消息是中文原文，不翻译。
- **上游是研究原型**：`nuclear-dev-agent` 以 `dsh-superagent` 原型为骨架（见
  [FORK.md](../nuclear-dev-agent/FORK.md)），`engines` 与 DSH 版本要对齐；上游升级按 FORK.md 合并后需重新验证。
- **不给 agent 特权**：执行器仍以操作者系统用户、`danger-full-access` 运行，
  门禁与人工批准边界不因宿主变化而改变。
