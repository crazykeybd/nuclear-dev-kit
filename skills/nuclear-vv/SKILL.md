---
name: nuclear-vv
description: 核能数值软件独立验证与确认 Skill。用于执行代码验证、解的验证和确认，记录参考解、收敛阶、基准来源、误差、适用域、不确定性与独立性。
license: MIT
metadata:
  version: "0.1.0"
---

# 独立验证与确认

## 1. 目标

从独立视角判断软件是否按设计正确实现、数值解是否随离散细化收敛，以及在声明适用域内是否与可信基准一致。V&V 结论必须由真实活动和证据支撑。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 执行者与审核者必须不同、均声明独立，且不属于开发组织；最终批准人还要独立于执行者、审核者和开发组织。
- 代码验证必须引用可追溯参考解；解的验证必须有收敛研究和实际观测阶；确认必须有可信基准来源、适用域、不确定性和误差指标。
- 独立性冲突、基准不可追溯、误差超限或结果失败时必须停止，不得用文字说明掩盖。
- V&V 不替代监管审查，也不得由 Agent 生成人工批准。
- 不得挑选有利数据、隐藏发散算例或把经验拟合称为独立确认。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/vv/vv-report.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate vv --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 制定独立 V&V 计划，把需求、设计、模块和测试映射到代码验证、解的验证与确认活动。
2. 对关键算法与实现执行代码验证，比较解析解、制造解或独立参考实现，记录差异和容差。
3. 执行网格/时间步收敛研究，报告观测阶、理论阶、拟合方法和异常区间。
4. 针对目标应用域选择有来源的基准题或实验数据，定义输入不确定性、模型不确定性和比较指标。
5. 由独立执行者和审核者复核方法、证据和结论，记录偏差、限制、残余风险与适用域。
6. 更新 `VV --validates--> REQ`、`VV --uses--> TEST` 节点与关系；产物稳定后停止，等待真实人员签署。

本阶段门禁关注点：

- 独立执行者、审核者和组织关系满足要求。
- 三种活动均存在且结果、证据为 `passed`。
- 代码验证含参考解；解的验证含收敛研究和观测阶；确认含基准、适用域、不确定性、误差与趋势。
- 所有确认需求均有 V&V 覆盖，所用测试关系真实。
- 最终批准人独立性由人工检查，Agent 不生成或补写批准。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate vv --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

V&V 产物和证据稳定后停止。把 `.nuclear-dev/stages/vv/vv-report.json`、V&V 证据以及待批准范围交给具备权限的真实人员独立审查。最终批准人必须独立于执行者、审核者和开发组织。

`.nuclear-dev/approvals/vv.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
