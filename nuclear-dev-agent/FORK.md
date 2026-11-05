# 来源与本仓库的改动（fork）

本目录 `nuclear-dev-agent/` 是**本仓库的主体**：一个 DSH（DeepSeek Harness）bundle，在
上游 `dsh-superagent` 原型的基础上改造成「核能软件开发智能体」，把 `nuclear-dev-kit`
的七阶段门禁接进「主动接活 → 开 Ticket → 独立 Session 执行 → 回帖」这条链路。

| 项 | 值 |
|---|---|
| 上游仓库 | https://github.com/deepseek-ai/dsh-superagent-prototype |
| 上游基点提交 | `8c32a9dc5d72c033816c6a8110b37f40cf94fba4`（main） |
| 首次复制日期 | 2026-11-05 |
| 许可证 | MIT，见同目录 `LICENSE`（上游版权归 DeepSeek Harness Team） |
| 上游文档 | 同目录 `README.md`、`SETUP.md`、`docs/` |

> 上游首段写明：这是**研究原型，非官方产品**，可能有 bug，工程实践不一定一致，用于自有环境
> 前须自行审查与适配。本目录在上游基础上继续改造，同样不承诺生产可用性。

## 相对上游改了什么

从 PR「重构：以 superagent 为主体融入 nuclear-dev-kit」开始，本目录不再是只读副本：

1. **身份**：包名与插件 id `dsh-superagent*` → `nuclear-dev-agent*`，环境变量前缀
   `DSH_SUPERAGENT_` → `DSH_NUCLEAR_DEV_AGENT_`，面板名「Superagent」→「核能研发智能体 /
   Nuclear Dev Agent」，客户端命名空间 `nuclearDevAgent`。
2. **核能域**（新增 `src/nuclear/`）：七阶段表、kit 解析、以及把 `nuclearctl.py`
   当子进程调用的桥接。**门禁判定只来自 `nuclearlib.py`**，这个包不复制任何规则。
3. **应用层**（新增 `src/app/nuclear.ts`、`src/app/views/nuclear.ts`）：按工单目录缓存扫描
   结果，向面板与概览提供阶段板；管理 API 增加 `GET nuclear` 与 `POST nuclear/refresh`，
   工单详情页在有 `.nuclear-dev` 工作区时带上 `nuclear` 阶段快照。
4. **提示词**（新增 `prompts/nuclear.md`，成为内置段落 `runtime/nuclear`）：七阶段、
   `nuclearctl.py` 的用法、以及「批准只能由人签署、门禁失败即停」的硬约束。
5. **执行环境**：新增 `DSH_NUCLEAR_DEV_AGENT_KIT`、`DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL`
   两个变量，指到本机 kit 与门禁命令行。
6. **部署配置**：`Config.nuclear`（`kitPath`、`python`、超时、刷新与工作区上限），
   由 `tools/deploy_nuclear_dev_agent.py` 写进 profile 的 `cordis.patch.yml`。

上游文件仍按原样保留结构，改动尽量集中在新增模块与命名上，便于对照上游阅读差异。

## 如何跟进上游

```bash
git clone https://github.com/deepseek-ai/dsh-superagent-prototype /tmp/upstream
cd /tmp/upstream && git checkout <新提交>
# 逐个文件对照，把上游改动并入本目录；不要整目录 --delete 覆盖，
# 本目录已含核能集成代码（src/nuclear/、src/app/nuclear.ts、src/app/views/nuclear.ts、
# prompts/nuclear.md），覆盖会丢失它们。
```

合并后更新本文件的「上游基点提交」与日期，并跑 `python3 tools/check_nuclear_dev_agent.py`
与 `cd nuclear-dev-agent && pnpm check`。
