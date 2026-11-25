# 变更记录

本文件记录使用者能感知的变化。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循[语义化版本](https://semver.org/lang/zh-CN/)。

判定规则变了、产物 Schema 变了、Skill 的指令变了、门禁行为变了，都算"使用者能感知"。
纯内部重构不算，但要能在 PR 里说清为什么不算。

## [Unreleased]

### 新增

- **过程资产库独立包**：`process-assets/` 收录由过程资产库 V5.0 切分出的 40 个文档模板/指引 Skill（p1–p9 + `process-asset-router`），按七阶段映射；提供只读查询 `assetctl.py` 与独立安装器，默认 dry-run，不影响核心十个 Skill 与门禁判定。阶段 Skill 与 agent prompt 加入条件引用。
- **核工程领域参考（按需加载）**：在 `skills/nuclear-dev/references/` 增加 15 篇领域参考与总索引
  `domain-index.md`，覆盖安全分级、适用标准、物理模型、核数据、数值方法、守恒、并行、HPC、
  可复现构建、测试模式、基准题、V&V、不确定性量化与配置/数据冻结。七个阶段 Skill 增加领域参考指针；
  标准、基准与核数据版本经联网核对并附来源。领域参考仅为工程指导，不参与门禁判定。
- **只读领域命令**：`nuclearctl.py domain <阶段> [--json]` 列出该阶段的领域参考路径、摘要与免责声明，
  不要求项目已初始化。`nuclear-dev-agent` 的总控与阶段智能体按阶段路由读取这些参考，面板阶段行显示参考数量。
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
- `tests/test_register.py` 把 `Path.is_relative_to`（Python 3.9+）换成 3.7 兼容写法，
  与包声明的"Python 3.7.3+"一致。

## [0.1.0]

首个版本：十个 `nuclear-*` Skill（七阶段 + 总入口 + 安装 + 部署）、唯一门禁实现
`nuclearlib.py`、门禁 CLI `nuclearctl.py`、只读 MCP 服务端、A2A 远程 V&V 客户端与服务端、
审计链、多宿主安装器，以及 `nuclear-dev-agent`（总控智能体 + 七个阶段智能体）。
