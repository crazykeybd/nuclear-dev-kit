# 在 dsh-superagent 中使用核能门禁

本仓库把上游 `dsh-superagent` 原型代码复制到 [`superagent/`](../superagent/)（见
[VENDOR.md](../superagent/VENDOR.md)），并把本包的核能研发门禁嵌进它的工作流：
superagent 的每个 Ticket 在自己的 Session 里干活，Session 的项目级 Skill 根
`<工作目录>/.dsh/skills` 里放着十个 `nuclear-*` Skill，于是执行器按 `nuclear-plan` →
… → `nuclear-release` 的既有门禁流程干活，判定仍来自 `nuclearlib.py`。

> 工程边界不变：不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> superagent 只是执行宿主，不会让门禁变松，也不会产生批准文件。

## 为什么是「装进工作目录」而不是改上游代码

- DSH 的 `@deepseek-ai/dsh-skill-filesystem` 按 `rank` 扫描 `<项目根>/.dsh/skills`
  （项目根 = 最近的含 `.git` 的祖先目录，Git worktree 的 `.git` 文件同样算）；
- superagent 的执行器 Session 用 `standard` 预设起，工作目录就是 Ticket 的 checkout，
  所以装进这个 worktree 的 `.dsh/skills` 对执行器可见；
- 上游目录保持**零改动**，升级时整目录替换即可（做法见 `VENDOR.md`）。

## 一、准备

1. 上游副本构建（一次性）：

   ```bash
   cd superagent
   pnpm install
   pnpm build          # 生成 lib/，被 .gitignore 忽略，不入库
   ```

   需要 Node.js 22.19+ 或 24+、pnpm；其余前置条件见
   [`superagent/docs/006-deployment.md`](../superagent/docs/006-deployment.md)。

2. 专用 DSH profile（沿用上游建议，叫 `superagent`），与日常用的 profile 分开：

   ```bash
   dsh superagent --from-default-profile web --dump-config > /dev/null
   dsh plugin --profile superagent add "link:$PWD/superagent"
   ```

   并把 `dsh-superagent` 写进该 profile `package.json` 的 `dsh.profile.bundles`。

3. 本包的 MCP 面（可选，让门禁变成确定性工具调用）：

   ```bash
   export NUCLEAR_DEV_MCP_SERVER="$PWD/skills/nuclear-dev/scripts/nuclearmcp.py"
   dsh plugin --profile superagent add "link:$PWD"
   ```

   详见 [README 的 DSH 小节](../README.md#deepseek-harness-dsh-支持) 与 `INSTALL.md` 4.6。

## 二、把核能 Skill 装进每个 Ticket 的工作目录

superagent 的「Execution」设置里有一个 prepare 命令，每个新 Ticket 在启动执行器前先跑它。
在它后面追加一条安装命令即可（`$DSH_SUPERAGENT_DIR` 是该 Ticket 的工作目录）：

```sh
git -C /home/me/src/my-nuclear-proj fetch --no-tags "https://github.com/$DSH_SUPERAGENT_GITHUB_REPOSITORY.git" "${DSH_SUPERAGENT_GITHUB_PR_HEAD:-HEAD}:refs/dsh-superagent/$DSH_SUPERAGENT_TICKET" &&
git -C /home/me/src/my-nuclear-proj worktree add -b "agent/$DSH_SUPERAGENT_NAME" "$DSH_SUPERAGENT_DIR" "refs/dsh-superagent/$DSH_SUPERAGENT_TICKET" &&
python3 /home/me/src/nuclear-dev-kit/skills/nuclear-setup/scripts/install.py dsh \
  --scope project --project "$DSH_SUPERAGENT_DIR" --yes --json
```

三条要点：

- 第三条用本包现成的安装器（与其它宿主同一个，不复制规则），目标正是
  `<工作目录>/.dsh/skills`；
- 工作目录已存在时安装器**默认以冲突退出**（退出码 `1`），prepare 随之失败、Ticket 报
  `The prepare command failed: …`，不会假装成功。要覆盖旧副本再加 `--force`（写入前备份）；
- superagent 只在目录不存在时跑 prepare，所以「续跑同一个 Ticket」不会重复安装。

## 三、验证

1. **Skill 可见**：在 `superagent` profile 的 Session 里看 Skill 目录，应有十个
   `nuclear-*`；或直接检查工作目录：

   ```bash
   ls "$DSH_SUPERAGENT_DIR/.dsh/skills"    # nuclear-dev … nuclear-release
   ```

2. **门禁可跑**：在工作目录里执行只读检查，`status` 应返回七阶段状态：

   ```bash
   python3 /home/me/src/nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py \
     --root "$DSH_SUPERAGENT_DIR" status --json
   ```

   全新项目 `gate plan` 返回 `1` 属预期；门禁通过不等于监管批准。

3. **端到端**：让允许列表里的账号在目标仓库的 Issue 上 `@<agent 账号> 用 nuclear-plan 开始第一阶段`。
   约一分钟后 Ticket 出现在面板上，执行器的第一件事应是只读检查而不是直接写文件。

## 四、已知限制

- **未在本机跑通端到端**：本仓库只验证到「prepare 命令把十个 Skill 装进 worktree」「门禁 CLI
  在该 worktree 上能返回真实状态」，没有真的等一个 GitHub Issue 变成 Ticket 并跑完一个阶段。
- **prepare 需要能让安装器执行的 Python**：目标机器要有 Python 3.7.3+（只用标准库）；
  没有的话第三条会失败，Ticket 会被标记失败而不是降级。
- **上游是研究原型**：npm 依赖、DSH 版本范围都要与 `superagent/package.json` 的 `engines`
  对齐；上游升级后本包需要重新验证。
- **两个 bundle 分别安装**：本包的 MCP/技能包与上游 `dsh-superagent` 是两个包，各自
  `dsh plugin add link:`；没有合并成单包，是为了让上游副本能被整目录替换。
- **不给 superagent 特权**：执行器仍以操作者系统用户、`danger-full-access` 运行，
  门禁与人工批准边界不因宿主变化而改变。
