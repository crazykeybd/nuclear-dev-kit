# 在 dsh-superagent 中使用核能门禁

本仓库把上游 `dsh-superagent` 原型代码复制到 [`superagent/`](../superagent/)（见
[VENDOR.md](../superagent/VENDOR.md)），并把本包的核能研发门禁嵌进它的工作流。
**部署只需要一条命令**，不用逐项配 bundle、环境变量或 prepare 命令。

> 工程边界不变：不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> superagent 只是执行宿主，不会让门禁变松，也不会产生批准文件。

## 一条命令部署

```bash
python3 tools/deploy_superagent.py            # 先预览：列出会做什么，不写任何文件
python3 tools/deploy_superagent.py --yes      # 确认后执行
```

它按顺序做这些事，每步都在 JSON 里留痕：

| 步骤 | 做什么 | 为什么 |
|---|---|---|
| build | 在 `superagent/` 里 `pnpm install && pnpm build` | 入库的是源码，`lib/` 按上游 `.gitignore` 不入库；缺 Node/pnpm 时预览会标出来，执行阶段直接报错而不装一半 |
| skills | 把十个 `nuclear-*` 装到 `$DSH_HOME/skills` | DSH 的**用户级** Skill 根，所有 profile 与 Ticket 工作目录都能看到 |
| profile | `dsh <profile> --from-default-profile web --dump-config` | profile 不存在时由 DSH 模板创建，已存在则沿用 |
| link | `dsh plugin --profile <profile> add link:<superagent>`，再 `link:<本仓库>` | 把两个 bundle 链接进 profile |
| bundles | 把 `dsh-superagent`、`nuclear-dev-kit` 补进 `package.json` 的 `dsh.profile.bundles` | 这一步 `dsh plugin` 不管，只能改文件 |
| patch | 写 profile 的 `cordis.patch.yml`：面板端口、`stateDir`、`nuclear-dev` 的 MCP 桥接（绝对路径） | 用绝对路径，所以不需要任何环境变量 |
| verify | `dsh --profile <profile> --dump-config` 复核这些行确实在组合结果里 | 防止“配置写了但没生效” |

常用参数：

```bash
--profile superagent      # 目标 profile，默认 superagent
--port 3082               # 面板端口
--dsh-home <路径>          # DSH home，默认 $DSH_HOME 或 ~/.dsh
--vendor-dir <路径>        # 上游副本目录，默认本仓库的 superagent/
--skip-build              # 已经构建过时跳过 pnpm（要求 lib/ 存在）
--refresh                 # 即使十个 Skill 已在位也强制重装（安装器会先备份）
--json                    # 机器可读输出
```

默认 dry-run；`--yes` 才写文件。改 `package.json` 与 `cordis.patch.yml` 之前会写
`<文件名>.<UTC 时间戳>.bak` 备份。**已有配置不会被覆盖**：`cordis.patch.yml` 里已有同 id 的行
（比如你自己的 `webserver` 端口、`llm` 供应商）原样保留，缺的那几块追加在文件末尾；预览时
会把「需补什么 / 保留什么」直接打出来。重复执行是安全的：Skill 已装齐就跳过，bundle 与
patch 行已在位就不重写。

部署完还有两件事必须由人来定，脚本不代填：

1. 面板 Sources 里填目标仓库与 agent 账号的 `gh` 包装器，Policy 里填允许名单；
2. 模型供应商若未配置，用面板 Settings 或在 profile 的 `cordis.patch.yml` 里补 `llm` 行。

启动：`dsh superagent`，面板 `http://127.0.0.1:3082`。

## 为什么核能 Skill 装在用户级目录

- DSH 的 `@deepseek-ai/dsh-skill-filesystem` 同时扫 `$DSH_HOME/skills`（用户级）与
  `<项目根>/.dsh/skills`（项目级），项目根是「最近的含 `.git` 的祖先」；
- 装到用户级后，superagent 的主 Session 与每个 Ticket 的执行器 Session 都直接看得到
  `nuclear-*`，**不需要**改 prepare 命令，也不用来回往工作目录里复制；
- 门禁判定仍然只有 `skills/nuclear-dev/scripts/nuclearlib.py` 一处，superagent 侧不做任何规则复制；
- 上游目录保持零改动，升级时整目录替换即可（做法见 `VENDOR.md`）。

## 备选：只装进某个 Ticket 的工作目录

需要「某个仓库锁一套 Skill 版本」时，可以改成装进该 Ticket 的 worktree——在 superagent 的
prepare 命令后面追加一条安装命令（`$DSH_SUPERAGENT_DIR` 是该工作目录）：

```sh
git -C /home/me/src/my-nuclear-proj fetch --no-tags "https://github.com/$DSH_SUPERAGENT_GITHUB_REPOSITORY.git" "${DSH_SUPERAGENT_GITHUB_PR_HEAD:-HEAD}:refs/dsh-superagent/$DSH_SUPERAGENT_TICKET" &&
git -C /home/me/src/my-nuclear-proj worktree add -b "agent/$DSH_SUPERAGENT_NAME" "$DSH_SUPERAGENT_DIR" "refs/dsh-superagent/$DSH_SUPERAGENT_TICKET" &&
python3 /home/me/src/nuclear-dev-kit/skills/nuclear-setup/scripts/install.py dsh \
  --scope project --project "$DSH_SUPERAGENT_DIR" --yes --json
```

工作目录已存在时安装器默认以冲突退出（码 `1`），prepare 随之失败、Ticket 报
`The prepare command failed: …`，不会假装成功；确需覆盖再加 `--force`（写入前备份）。

## 验证

1. **部署自检**：`python3 tools/deploy_superagent.py --json` 里 `verify` 一步的
   `missing_rows` 应为空。
2. **Skill 可见**：`ls "$DSH_HOME/skills"` 应有十个 `nuclear-*`；superagent 的 Session
   里也能在 Skill 目录看到它们。
3. **门禁可跑**：在工作目录里跑只读检查，`status` 应返回七阶段状态：

   ```bash
   python3 /home/me/src/nuclear-dev-kit/skills/nuclear-dev/scripts/nuclearctl.py \
     --root "$DSH_SUPERAGENT_DIR" status --json
   ```

   全新项目 `gate plan` 返回 `1` 属预期；门禁通过不等于监管批准。

4. **端到端**：让允许列表里的账号在目标仓库的 Issue 上 `@<agent 账号> 用 nuclear-plan 开始第一阶段`。
   约一分钟后 Ticket 出现在面板上，执行器的第一件事应是只读检查而不是直接写文件。

## 已知限制

- **端到端没有在本仓库跑通**：已验证到「部署命令把 Skill/bundle/patch 都放对位置」「门禁 CLI
  在 worktree 上返回真实状态」「`dsh --dump-config` 里这些行确实存在」，没有真的等一个
  GitHub Issue 变成 Ticket 并跑完一个阶段。面板里的 Source/Policy/模型供应商仍需人配置。
- **需要 Node 工具链**：`superagent/` 入库的是源码，第一次部署要 `pnpm install && pnpm build`
  （Node.js 22.19+ 或 24+）。没有 Node 的机器只能装 Skill、用不了 superagent。
- **两个 bundle、一次部署**：脚本会链接两个包，但没有把上游合并进本包——让上游副本可整目录
  替换，比省一次 `link` 更重要。
- **上游是研究原型**：`engines` 与 DSH 版本要对齐；上游升级后需重新验证（`VENDOR.md` 有升级步骤）。
- **不给 superagent 特权**：执行器仍以操作者系统用户、`danger-full-access` 运行，
  门禁与人工批准边界不因宿主变化而改变。
