# 过程资产与七阶段的映射

本文件说明 `process-assets/skills/` 的 40 个 Skill 如何映射到 nuclear-dev-kit 的七阶段门禁流程。

## 映射原则

- 七阶段 Skill（`nuclear-*`）定义**受控流程与判定**：产物 JSON、证据、追溯、门禁、人工批准。
- 过程资产 Skill（`pX-*`）定义**要交付的工程文档**：正式报告、评审单、矩阵、大纲、PPT、数据表单。
- 二者不互相替代：阶段 Skill 负责"做与证"，资产 Skill 负责"写成单位规定的正式文件"。
- 映射是**建议关系**，不是门禁规则；不参与 `nuclearlib.py` 判定。

## 七阶段 → Skill

### plan（软件策划）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p1-software-naming-review` | 软件命名评审单 | 软件正式命名前的评审，记录分类与重名核查 |
| `p1-software-naming-rules` | 软件命名规则 | 需要命名/版本升级建议时 |
| `p2-config-management-plan-guide` | 配置管理计划编制指引 | 写策划报告 4.11 配置管理节 |
| `p2-kickoff-meeting-deck` | 项目启动会议 PPT | 项目启动会 |
| `p2-management-standards-guide` | 管理标准与程序指引 | 写策划报告 2.1 遵循标准节 |
| `planning-report-template` | 软件策划报告 | 形成正式策划报告正文 |

### requirements（需求分析）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p3-requirements-analysis-report` | 需求分析报告 | 形成正式需求分析报告 |
| `p3-requirements-review-sheet` | 需求过程评审单 | 需求评审 |
| `p3-requirements-traceability-matrix` | 需求跟踪矩阵 | 建立/维护需求追踪 |

> `p3-requirements-traceability-matrix` 与 `.nuclear-dev/traceability.json` 是两种表现：前者是单位规定的 XLSX 正式文件，后者是门禁校验的机器可读账本。两者内容应一致，不能只维护一侧。

### design（软件设计）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p4-theoretical-model-report` | 理论模型报告 | 写控制方程、本构、假设、适用范围 |
| `p4-design-report` | 设计报告 | 总体/详细设计、接口、需求映射 |
| `p4-design-review-sheet` | 设计过程评审单 | 设计评审 |

### implementation（编码实现）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p5-dev-notes` | 模块开发笔记 | 每个 MOD 的实现记录 |
| `p5-unit-test-execution-record` | 单元测试执行记录表 | 实现阶段自测记录 |
| `p5-user-manual` | 用户手册 | 随代码交付的使用说明 |

### test（软件测试）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p6-test-plan` | 测试计划 | 测试策划 |
| `p6-test-report` | 测试报告 | 测试执行后汇总 |
| `p6-static-defect-explanation` | 静态测试缺陷解释表 | 致命/严重静态缺陷解释 |
| `p6-testcase-review-sheet` | 测试用例评审单 | 用例评审 |
| `p6-unittest-execution-guide` | 单元测试执行指引 | 覆盖率与工具约定 |

### vv（独立验证与确认）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p7-vv-outline` | V&V 大纲 | 独立 V&V 策划 |
| `p7-vv-report` | V&V 报告 | 独立 V&V 结果 |
| `p7-vv-review-sheet` | 验证过程评审单 | V&V 评审 |
| `p7-engineering-validation-record` | 工程验证记录表 | EV 用例执行记录 |

数据管理子组（归 `vv`，跨阶段可用）：

`p7-data-attribute-list`、`p7-data-description-file`、`p7-data-error-correction`、`p7-data-in-out-approval`、`p7-data-maintenance`、`p7-data-use-application`

这些表单服务于核数据/输入数据的受控管理；数据版本变化会影响 V&V 结论与发布冻结，详见领域参考 `nuclear-data.md` 与 `configuration-and-data-freeze.md`。

### release（软件发布）

| Skill | 名称 | 何时用 |
|---|---|---|
| `p8-release-baseline-a` / `-b` / `-nonsafety` | 发布基线配置表 | 安全 A / B / 非安管理类基线 |
| `p8-release-baseline-method` | 发布基线建立方法 | SVN trunk→tag 基线 |
| `p8-release-process-guide` | 正式版本发布指引 | 发布流程与检查单 |
| `p8-release-review-deck-a` / `-nonsafety` | 发布评审 PPT | 安全 A / 非安管理类评审 |
| `p8-release-review-meeting-guide` | 发布评审会指引 | 会前/会中/会后 |
| `p9-script-description` | 脚本说明书 | 安全脚本全过程说明 |

## 路由

用户说"生成测试计划"但未提阶段时，`process-asset-router` 按文档名反查阶段（`测试计划`→`test`）；用户说"安全 A 类发布基线"时直接映射 `p8-release-baseline-a`。多文档需求按阶段顺序逐个分发。

## 边界

- 资产 Skill 生成的正式文档若被阶段产物引用为证据，必须通过 `nuclearctl.py evidence add` 登记真实文件与结果；文档本身不等于证据通过。
- 评审单的签字栏由真实人员填写；Agent 不代替签署，也不生成批准文件。
- 数据入库/升版审批单由具备权限人员签署；Agent 只生成表单。
