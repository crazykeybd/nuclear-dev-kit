# 核工程领域参考索引

本索引把七阶段流程指向可按需加载的领域参考。它只提供**工程指导**，不参与门禁判定；门禁的唯一事实来源仍是 `scripts/nuclearlib.py`。所有参考文档为**参考性材料**，不替代适用标准原文、法规解释或持证人员判断。

## 使用规则

1. 进入某阶段时，先按本表读取该阶段领域参考与检查清单，再动阶段产物。
2. 参考中的标准编号、版本、基准题来源必须按项目所在地法规和适用范围复核；不得把行业惯例冒充强制要求。
3. 未知或不适用的领域条目写入 `open_items`，不得用占位值伪装完成。
4. `nuclearctl.py domain <阶段>` 可只读列出本阶段的参考路径与检查清单；该命令不改变门禁结论。

## 阶段 → 参考文档

| 阶段 | 触发场景 | 参考文档 |
|---|---|---|
| plan | 安全分级、适用标准、工具鉴定、V&V 策略 | [安全分级与 V&V 等级](safety-classification.md)、[适用标准谱系](nuclear-standards.md) |
| requirements | 物理模型、核数据、指标与验收写法 | [物理模型需求](physical-models.md)、[核数据与单位](nuclear-data.md)、[需求模式](requirement-patterns.md) |
| design | 数值方法、离散守恒、并行与误差 | [数值方法](numerical-methods.md)、[离散化与守恒](discretization-conservation.md)、[并行设计](parallel-design.md) |
| implementation | HPC 实现、可复现构建、数据结构 | [HPC 实现](hpc-implementation.md)、[可复现构建](reproducible-builds.md) |
| test | 测试矩阵、基准题、MMS 与负向测试 | [测试模式](test-patterns.md)、[基准题目录](benchmark-catalog.md) |
| vv | 代码验证、解的验证、确认与 UQ | [V&V 方法](vv-methods.md)、[不确定性量化](uncertainty-quantification.md) |
| release | 核数据冻结、配置/SBOM/回滚 | [配置与数据冻结](configuration-and-data-freeze.md) |

## 来源层级约定

每篇领域参考对其依据标注以下一种层级：

- **法规/强制标准**：项目所在地法规或合同采购明确要求的文件；必须由持证人员确认适用性。
- ** consensus 标准**：IEEE/IEC/ASME/ISO 等标准组织发布的标准；是否强制取决于合同与监管框架。
- **公开教材/综述**：权威教材、综述或研究机构技术报告；用于工程方法指导，不构成合规依据。
- **工程惯例**：行业常见做法；仅作提示，必须项目内确认。

## 可追溯性

领域参考不改变 Schema、不新增阶段产物、不提供批准工具。阶段产物引用参考时，只引用公开可核查的文件名、标准编号与版本；引用来源不明的内容应进入 `open_items`。
