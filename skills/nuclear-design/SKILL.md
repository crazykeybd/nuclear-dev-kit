---
name: nuclear-design
description: 核能数值软件设计 Skill。用于把 REQ 需求分配为 DES 设计项，并记录架构、控制方程、离散格式、稳定性、守恒、误差分析和验证计划。
license: MIT
metadata:
  version: "0.1.0"
---

# 软件设计

## 1. 目标

给每条需求一个可实现、可审查、可验证的技术解，并证明数值方法在声明适用域内具备一致、稳定和受控误差的工程基础。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 设计不得只写软件模块名；必须说明物理模型、方程、假设、边界、离散和求解流程。
- 稳定性、守恒和误差分析必须有具体方法或判据，不能以“经验证稳定”代替依据。
- 每个 REQ 至少分配到一个 DES；每个 DES 的 `requirements` 与追溯关系必须一致。
- 数值格式、时间推进、线性/非线性求解、并行分解和数据类型选择应说明影响及限制。
- 设计变更必须回看受影响需求、接口、测试和 V&V 计划；不得静默改变物理含义。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/design/design.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate design --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 建立架构总览和组件边界，明确每个组件的责任、接口、数据所有权和错误传播方式。
2. 建立数学模型，逐项记录控制方程、守恒量、本构关系、初始与边界条件、单位和符号。
3. 说明空间、时间或相空间离散格式、网格要求、时间步限制、线性化与耦合求解策略。
4. 分析稳定性、守恒性、数值耗散/色散、舍入与截断误差，并定义可验证的误差控制手段。
5. 把每条 REQ 分配到一个或多个 `DES-NNN`，为设计项写明算法、数据结构、接口、错误控制和验证计划。
6. 执行设计评审与接口核对，更新追溯 `REQ --allocated_to--> DES`，把未闭合问题写入开放项。

本阶段门禁关注点：

- 架构组件非空，责任与接口可实施。
- 数学模型完整覆盖方程、假设、适用范围、离散、稳定性、守恒和误差分析。
- 设计项字段完整，状态合法。
- 所有 REQ 均分配至实际 DES，DES 反向关联与追溯一致。
- 设计限制和未决问题可追踪，不以占位值掩盖。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate design --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/design/design.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/design.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
