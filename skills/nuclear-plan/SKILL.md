---
name: nuclear-plan
description: 核能数值软件研发的第一阶段 Skill。用于确定安全分级、V&V 等级、适用标准、工具鉴定、人员资格、配置管理、开放项和独立 V&V 策略，并建立可审计的策划基线。
license: MIT
metadata:
  version: "0.1.0"
---

# 软件策划

## 1. 目标

把“要开发什么、按什么等级控制、凭什么判定可信、由谁在什么工具和配置下完成”写成可审查、可执行、可追溯的软件策划。此阶段不是填模板，而是建立后续需求、设计、实现、测试、V&V 和发布共同遵守的工程边界。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 安全分级和 V&V 等级必须给出项目依据与适用标准来源；不得由 Agent 自行宣布监管合规。
- 独立 V&V 必须启用；执行者、审核者和最终批准人的独立性约束从策划阶段开始设计。
- 工具鉴定只记录实际状态。未完成鉴定的工具不得写成 `qualified`；人员未提供真实资格证据时不得写成 `qualified`。
- 配置管理必须明确版本库、基线、变更控制和备份，使后续每个构建与证据能够回指受控版本。
- 开放项只能以 `closed` 解除门禁；`accepted` 仍阻断。未知内容必须保留为开放项，不得用占位字符串伪装完成。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/plan/plan.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate plan --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 从任务、危害和后果出发确定安全分级，记录分级依据、排除项和待确认边界；涉及监管解释时标记为需要真实专业人员判断。
2. 依据软件风险、物理模型复杂度和独立 V&V 要求确定 V&V 等级；规定代码验证、解的验证与确认的方法组合。
3. 建立适用标准清单，写明编号、标题、版本、适用性、状态和可审计来源；不把一般行业惯例冒充强制标准。
4. 逐项鉴定开发、构建、测试和 V&V 工具，记录版本、用途、鉴定状态、依据和限制。
5. 落实岗位资格、人员指派与证据，建立基线、变更控制、备份和可恢复策略。
6. 在 `open_items` 中记录尚未闭合的技术或管理事项、负责人和影响；只有真实关闭后才改为 `closed`。

本阶段门禁关注点：

- `project` 的安全分级、分级依据、V&V 等级和依据完整且非占位。
- 至少一项标准为 `applicable`，且标准版本与来源可追溯。
- `vv_strategy.independence_required` 为 `true`，验证方法非空。
- 工具无 `pending`，人员均为 `qualified` 且有资格证据。
- 配置管理四项齐全，开放项全部为 `closed`。

## 6. 证据登记

每个被阶段产物引用的证据都必须在项目内实际存在，并通过真实 CLI 登记：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> evidence add <项目内文件> \
  --kind <类型> --producer <真实生产者> --command <实际命令或可审计操作> \
  --result <passed|failed|observed|not_applicable> --json
```

只从返回 JSON 的 `evidence.id` 读取 `EVID-NNN`。同一路径不得重复登记；内容变化时保留原始记录并新增可审计证据。失败、未执行或不适用的结果必须如实记录，不能改写为 `passed`。

## 7. 追溯更新

增量维护 `.nuclear-dev/traceability.json` 的 `nodes` 与 `links`，只使用共享 Schema 允许的关系。相关阶段关系为：

```text
REQ --allocated_to--> DES
DES --implemented_by--> MOD
TEST --exercises--> MOD
TEST --verifies--> REQ
VV --validates--> REQ
VV --uses--> TEST
REL --contains--> REQ
REL --contains--> MOD
```

节点标题和阶段产物中的关联字段必须与追溯一致。不得只追加关系而遗漏节点，也不得留下孤立或反向不一致的条目。

## 8. 结束检查

完成本阶段真实活动后依次执行并读取退出码与 JSON：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate plan --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/plan/plan.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/plan.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
