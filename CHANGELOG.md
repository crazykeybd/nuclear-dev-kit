# 变更记录

本文件记录使用者能感知的变化。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循[语义化版本](https://semver.org/lang/zh-CN/)。

判定规则变了、产物 Schema 变了、Skill 的指令变了、门禁行为变了，都算"使用者能感知"。
纯内部重构不算，但要能在 PR 里说清为什么不算。

## [Unreleased]

### 新增

- **门禁运行轨迹（trace）**：`nuclearctl.py gate <阶段> --trace` 把这次判定记成一条可校验的记录，
  包含 span 树、内核原话、当时的产物与批准摘要、以及运行环境（内核版本、`rules_sha256`、Python 与平台）。
  记录自校验并串成链，`nuclearctl.py trace list|show|verify` 查看与校验；产物事后变更只报"偏离"，
  不算篡改。默认关闭，可用 `NUCLEAR_DEV_TRACE=1` 默认打开。写轨迹失败不改变门禁结论与退出码。
  标准见 `skills/nuclear-dev/references/tracing.md`。
- **工作区体检**：`nuclearctl.py doctor` 一次给出环境、工作区结构、阶段进展、轨迹链与审计链的结论，
  只读、不写文件。`ok` 表示"工作区完好"，不是"七个阶段都通过了"。
- `docs/raven-alignment.md`：参考 Raven 的评估结论——采纳了轨迹纪律、体检与仓库治理；
  拒绝了 DAG 编排、记忆插件化、evolver 评测闭环与 agent 目录注册表，并写明理由。
- `CONTRIBUTING.md`、`CHANGELOG.md`、`.github/pull_request_template.md`：把"门禁规则只有一份""没有批准通道"
  "离线确定"三条约束写进贡献流程，并给出"加一个阶段要动哪几处"的清单。

### 修正

- `INSTALL.md` 的包结构里过时的测试项数改为与当前用例数一致。

## [0.1.0]

首个版本：十个 `nuclear-*` Skill（七阶段 + 总入口 + 安装 + 部署）、唯一门禁实现
`nuclearlib.py`、门禁 CLI `nuclearctl.py`、只读 MCP 服务端、A2A 远程 V&V 客户端与服务端、
审计链、多宿主安装器，以及 `nuclear-dev-agent`（总控智能体 + 七个阶段智能体）。
