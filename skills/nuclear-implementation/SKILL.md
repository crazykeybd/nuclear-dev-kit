---
name: nuclear-implementation
description: 核能数值软件实现 Skill。用于将 DES 设计落实为真实源码 MOD 模块，保持源码工作区干净，执行可复现构建并登记构建证据。
license: MIT
metadata:
  version: "0.1.0"
---

# 编码实现

## 1. 目标

在受控源码基线上实现与设计一致、可构建、可测试、可复现的软件模块，并用真实路径和构建证据证明实现存在。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 模块路径必须位于项目内且真实存在；不得用计划中的路径或空目录冒充实现。
- `source_control.dirty` 必须为 `false`。若工作区未纳入版本控制，应由项目配置管理记录实际基线，不能伪造 revision。
- 构建证据必须是 CLI 登记的 `passed` 证据，命令、环境、版本和结果可复现。
- 实现必须保持设计语义；偏离设计时先更新设计和追溯，不得只在代码中暗改。
- 静态分析、单元测试和编译失败均是有效证据；不得删改结果或只保留成功片段。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/implementation/implementation.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate implementation --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 读取 DES、接口和验证计划，建立源码模块、公共数据结构和错误处理约定。
2. 实现求解流程、物性/本构接口、边界条件、并行通信、I/O 与诊断，保持单位与符号一致。
3. 编写或更新单元测试与静态分析配置，处理编译警告、未定义行为、资源生命周期和数值异常。
4. 在声明的编译器、依赖、MPI、操作系统和容器环境中执行干净构建，保留原始日志与退出码。
5. 把每个 DES 通过 `implemented_by` 映射到 `MOD-NNN`，在模块中登记真实路径、入口点、测试和设计 ID。
6. 登记构建与静态分析证据，重新运行阶段门禁；任何失败都保留诊断并回到设计或实现修正。

本阶段门禁关注点：

- 源码基线 revision 与 clean 状态有依据。
- 构建环境、编译器、依赖、MPI、OS 和容器信息完整。
- 所有 MOD 路径真实存在，入口点非空。
- 构建证据均存在且结果为 `passed`。
- 所有 DES 映射到实际 MOD，追溯与模块 `design_ids` 一致。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate implementation --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/implementation/implementation.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/implementation.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
