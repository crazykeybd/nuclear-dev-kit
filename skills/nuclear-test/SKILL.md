---
name: nuclear-test
description: 核能数值软件测试 Skill。用于设计并执行单元、模型和系统测试，覆盖守恒、边界、负向与回归，登记真实结果并证明每个 MOD 和 REQ 均被检验。
license: MIT
metadata:
  version: "0.1.0"
---

# 软件测试

## 1. 目标

以可复现测试暴露实现缺陷并形成需求级证据，而不是以测试数量代替覆盖质量。测试结论必须能够回到模块、需求、缺陷和受控源码版本。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 测试结果与证据结果必须为真实 `passed`；失败结果必须保留并进入缺陷处置。
- 必须覆盖 `unit`、`model`、`system` 三种等级以及 `conservation`、`boundary`、`negative` 三类关注点。
- 每个 MOD 必须有 `exercises` 关系，每条 REQ 必须有 `verifies` 关系。
- 守恒测试应检查质量、动量、能量或其他适用不变量及容差；边界与负向测试应覆盖声明限制和异常路径。
- 不得只运行成功子集、修改断言迁就实现，或把未执行测试写成通过。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/test/test-report.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate test --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 从需求和设计验证计划推导测试矩阵，明确等级、关注点、模块、需求、输入、预期、容差和证据类型。
2. 实现可重复的单元测试，验证函数、数据结构、物性接口、边界处理和错误路径。
3. 构建模型级测试，验证方程离散、守恒、收敛、对称性、极限行为和网格/时间步影响。
4. 执行系统级场景与回归基线，记录操作系统、编译器、容器、源码 revision、输入和退出码。
5. 对失败建立缺陷与开放项，修复后重新执行相关测试并登记新证据；保留失败历史及其处置依据。
6. 更新 `TEST --exercises--> MOD`、`TEST --verifies--> REQ` 与节点标题，运行测试及门禁检查。

本阶段门禁关注点：

- 测试环境与源码 revision 完整。
- 三种 level 与 conservation、boundary、negative 均至少出现一次。
- 每项测试结果和引用证据均为 `passed`。
- 回归结果为 passed，且引用通过证据。
- 每个 MOD 与 REQ 均被测试追溯覆盖。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate test --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/test/test-report.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/test.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
