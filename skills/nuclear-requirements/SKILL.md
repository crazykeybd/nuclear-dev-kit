---
name: nuclear-requirements
description: 核能数值软件需求分析 Skill。用于把物理模型、数值精度、适用范围、接口、安全约束和验收方法写成可验证、可确认、可分配设计的 REQ 需求基线。
license: MIT
metadata:
  version: "0.1.0"
---

# 需求分析

## 1. 目标

将用户意图、物理问题和受控策划转化为无歧义、可观察、可验证的软件需求。每条需求都必须说明为什么存在、从哪里来、如何验收，以及后续应分配到哪里。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 需求描述必须使用可判定语言；避免“快速”“准确”“稳定”等没有指标、方法或适用条件的词。
- 物理模型必须写明守恒关系、本构或关联式、边界条件、适用范围、假设与限制。
- 接口需求必须定义数据、单位、坐标系、符号约定、精度、异常和兼容性；不得只写“提供接口”。
- 验收准则必须包含方法、容差和证据类型；不能把“测试通过”本身当作唯一准则。
- 不得编造用户需求、标准条款或实验依据；来源不明的内容应进入开放项并停止关键分配。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/requirements/requirements.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate requirements --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 读取策划基线，确认安全等级、V&V 等级、适用标准和工具限制，再把用户与工程输入逐条映射为需求。
2. 定义功能、性能、数值精度、守恒、边界、异常处理、数据接口、运行环境和可维护性需求。
3. 为每条需求建立唯一 `REQ-NNN`，写清陈述、理由、来源、优先级、安全类别、验证方法和是否需要确认。
4. 为每条需求建立一项或多项可执行验收准则，记录判据、方法、容差和所需证据类型。
5. 开展需求评审，检查冲突、遗漏、重复、不可测表述和跨专业接口；评审发现必须留有可审计记录。
6. 更新追溯节点，并为每条需求建立到后续设计的 `allocated_to` 意图；未分配的需求必须在开放项中说明。

本阶段门禁关注点：

- `scope` 的定义、适用性、排除项、假设和限制均具体。
- 需求 ID 使用 `REQ-NNN`，必填字段完整，状态与验证方法合法。
- 每项验收准则都有方法、容差和证据类型。
- 需求覆盖物理模型、精度、适用范围、接口与安全约束。
- 追溯中每个 REQ 都指向实际设计项，且设计项反向引用一致。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate requirements --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/requirements/requirements.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/requirements.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
