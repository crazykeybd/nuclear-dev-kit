---
name: nuclear-release
description: 核能数值软件发布 Skill。用于冻结语义版本、源码 revision、发布范围、SBOM、复现与回滚证据，并在递归门禁通过后生成确定性配置清单。
license: MIT
metadata:
  version: "0.1.0"
---

# 软件发布

## 1. 目标

把已验证的软件、依赖、构建配置、限制和恢复路径冻结为可重建、可审计、可回滚的发布候选。发布结论只描述已证明的范围。

## 2. 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

- 发布版本必须为语义版本，源码 revision 必须与实现阶段一致，发布范围路径必须真实存在。
- SBOM、复现和回滚证据必须实际生成、结果 `passed`，不得以空文件或计划代替。
- 发布必须覆盖全部 REQ 与 MOD；未覆盖项、未关闭开放项和失败证据均阻断。
- 配置清单只能在 release 递归门禁通过后生成；清单不是人工批准或监管认证。
- 不得删除已知限制、扩大适用域或把候选版本描述为已批准版本。

- 只在用户授权的工作区内修改实际工程产物；不得替用户宣称阶段已获批准。

## 3. 产物路径

本阶段唯一阶段产物为：

```text
.nuclear-dev/stages/release/release.json
```

保留已有内容并增量修改。输出使用 UTF-8 和 LF；新增或更新的工程文件必须实际存在。

## 4. 启动检查

先定位当前 `SKILL.md` 所在目录为 `SKILL_DIR`，确认项目根目录，并执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate release --json
```

读取实际输出并优先返回最早阻断阶段。仅有 `--no-dependencies` 可用于诊断当前阶段自身问题，不能据此宣称递归门禁通过。若工作区未初始化，先调用 `nuclear-setup`。

## 5. 真实工程活动

1. 冻结最终源码 revision、版本号、发布范围和配置，核对与实现阶段基线一致。
2. 生成并检查 SBOM，记录依赖版本、许可证或来源、漏洞/支持状态以及容器镜像身份。
3. 在清洁环境中按文档重建，验证产物摘要、测试/V&V 结果和安装步骤。
4. 准备并演练回滚，验证旧版本恢复、数据兼容和责任人可执行性证据。
5. 汇总已知限制、残余风险、开放项和发布范围，确认所有 REQ 与 MOD 由 `REL --contains-->` 覆盖。
6. release 递归门禁通过后运行 `manifest`；若返回冲突，审查差异并显式决定是否 `--force`，不得自动覆盖。

本阶段门禁关注点：

- 语义版本、revision 一致性和真实发布范围。
- SBOM 文件与通过证据存在。
- 复现和回滚均 `verified=true` 且有通过证据。
- 全部 REQ 与 MOD 纳入发布追溯。
- 递归门禁通过后才生成确定性配置清单。

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
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> gate release --json
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> validate --json
```

`gate` 失败返回 `1` 时保留阻断项并停止；参数或工具错误返回 `2` 时修正调用。不得通过修改门禁实现、删除证据或弱化验收准则制造通过。

## 9. 人工批准停止点

本阶段产物稳定后停止。把 `.nuclear-dev/stages/release/release.json` 和相关证据交给具备权限的真实人员独立审查；批准范围应包含当前阶段产物及项目要求一并冻结的文件。

`.nuclear-dev/approvals/release.json` 只能由真实人员创建和签署，字段包括 `stage`、`approver`、`decision`、`date`、`scope`、`artifact_sha256` 和 `statement`，且 `approver.actor_type` 必须为 `human`。Agent、Skill、安装器和 CLI 都不得创建、修改、推断或自动补全批准文件；产物变化后旧批准失效。

## 10. 共享 Schema 引用

- [阶段产物 Schema 与门禁契约](../nuclear-dev/references/artifact-schema.md)
- [七阶段受控工作流](../nuclear-dev/references/workflow.md)
- [门禁 CLI](../nuclear-dev/scripts/nuclearctl.py)
- [权威门禁实现](../nuclear-dev/scripts/nuclearlib.py)

Schema 与本 Skill 冲突时，以实际 CLI 报错和冻结的 `nuclearlib.py` 为准；停止并向用户报告冲突，不得自行放宽规则。
