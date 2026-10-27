# 阶段产物 Schema 与门禁契约

本文件是人员填写阶段产物、Agent 更新追溯和执行门禁时的操作说明。机器可执行规则以冻结的 `../scripts/nuclearlib.py` 为唯一权威；本文件与实现冲突时，以实际 CLI 报错和该实现为准，并停止修改而不是弱化门禁。

## 公共约定

所有阶段产物使用 UTF-8 编码的 JSON：

```json
{
  "schema_version": 1,
  "open_items": []
}
```

阶段产物路径固定如下：

| 阶段 | 文件 |
|---|---|
| plan | `.nuclear-dev/stages/plan/plan.json` |
| requirements | `.nuclear-dev/stages/requirements/requirements.json` |
| design | `.nuclear-dev/stages/design/design.json` |
| implementation | `.nuclear-dev/stages/implementation/implementation.json` |
| test | `.nuclear-dev/stages/test/test-report.json` |
| vv | `.nuclear-dev/stages/vv/vv-report.json` |
| release | `.nuclear-dev/stages/release/release.json` |

开放项可出现在支持的 `open_items` 数组中：

```json
{
  "id": "OI-001",
  "description": "尚未解决事项及影响",
  "status": "open",
  "owner": "负责人",
  "due": "可选日期"
}
```

`status` 只能为 `open`、`closed`、`accepted`。门禁只允许全部开放项为 `closed`；`accepted` 仍然阻断。未知信息不能写入占位值伪装完成。所有字符串值去首尾空格并转大写后，以下内容及 `TBD:` 前缀都会阻断：

```text
TBD
TODO
UNRESOLVED
UNKNOWN
DRAFT
PENDING
NOT RECORDED
IN PROGRESS
```

## 软件策划：plan

顶层字段：

```text
schema_version, project, standards, vv_strategy,
tool_qualification, personnel, configuration_management, open_items
```

`project` 必须包含：

```text
name, purpose, safety_classification, classification_basis, vv_level, vv_basis
```

`standards` 至少一项，每项包含：

```text
id, title, revision, applicability, status, source
```

`status` 为 `applicable`、`not_applicable` 或 `pending`。至少一项必须为 `applicable`。

`vv_strategy` 必须包含：

```text
levels, independence_required, verification_methods, validation_strategy
```

`levels` 和 `verification_methods` 必须非空，`independence_required` 必须为 `true`。

`tool_qualification` 至少一项，每项包含：

```text
tool, version, role, qualification_status, basis, limitations
```

`qualification_status` 为 `qualified`、`not_required` 或 `pending`；门禁阻断 `pending`。

`personnel` 至少一项，每项包含：

```text
role, required_qualification, assigned_person, evidence, status
```

`status` 为 `qualified` 或 `pending`。每个人必须为 `qualified`，且 `evidence` 非空。

`configuration_management` 必须包含：

```text
vcs, baseline, change_control, backup
```

## 需求分析：requirements

顶层字段：

```text
schema_version, scope, requirements, open_items
```

`scope` 必须包含：

```text
description, applicability, exclusions, assumptions, limitations
```

每项需求使用 `REQ-NNN`，包含：

```text
id, title, statement, rationale, source, priority, safety_class,
category, verification_method, validation_required,
acceptance_criteria, status
```

可增加 `interfaces`。`priority` 为 `critical`、`high`、`medium` 或 `low`；`verification_method` 为 `test`、`analysis`、`inspection` 或 `demonstration`；`status` 为 `defined` 或 `approved`。

`acceptance_criteria` 每项包含：

```text
id, criterion, method, tolerance, evidence_kind
```

`method` 和 `evidence_kind` 必须非空。需求应明确物理模型、数值精度、适用范围、接口和安全约束，验收准则必须可执行、可观察。

## 软件设计：design

顶层字段：

```text
schema_version, architecture, models, design_items, open_items
```

`architecture` 包含 `overview` 和至少一个 `components` 项。每个组件包含：

```text
id, name, responsibility, interfaces
```

`models` 至少一项，每项包含：

```text
id, name, equations, assumptions, applicability,
discretization, stability, conservation, error_analysis
```

`design_items` 至少一项，每项使用 `DES-NNN`，包含：

```text
id, title, requirements, description, algorithm, data_structures,
interfaces, error_control, verification_plan, status
```

`status` 为 `designed` 或 `approved`。门禁要求每个 `REQ` 至少有一条 `allocated_to` 关系指向 `DES`。

## 编码实现：implementation

顶层字段：

```text
schema_version, source_control, build, modules, build_evidence_ids, open_items
```

`source_control` 包含：

```text
repository, revision, branch, dirty
```

`dirty` 必须为 `false`。`build` 包含：

```text
system, compiler, compiler_version, flags, dependencies, mpi, os, container
```

每个模块使用 `MOD-NNN`，包含：

```text
id, title, design_ids, paths, language, entrypoints,
unit_tests, static_analysis, status
```

`status` 为 `implemented` 或 `approved`。`paths` 中每个路径必须在项目内真实存在；`entrypoints` 至少一项。`build_evidence_ids` 必须非空且只能引用结果为 `passed` 的证据。门禁要求每个 `DES` 至少有一条 `implemented_by` 关系指向 `MOD`。

## 软件测试：test

顶层字段：

```text
schema_version, environment, tests, regression, open_items
```

`environment` 包含：

```text
os, compiler, container, source_revision
```

每个测试使用 `TEST-NNN`，包含：

```text
id, title, level, category, module_ids, requirement_ids,
procedure, expected, actual, result, executed_at,
evidence_ids, defects
```

`level` 为 `unit`、`model` 或 `system`；`category` 为 `unit`、`model`、`system`、`conservation`、`boundary`、`negative` 或 `regression`。全部测试必须同时覆盖三种 `level`，以及 `conservation`、`boundary`、`negative` 三类关注点。

测试结果为 `passed` 才满足门禁，引用证据也必须为 `passed`。每个模块必须有 `exercises` 关系，每项需求必须有 `verifies` 关系。

`regression` 包含：

```text
baseline, result, evidence_ids
```

回归结果必须为 `passed`，其证据也必须为 `passed`。

## 软件验证与确认：vv

顶层字段：

```text
schema_version, independence, activities, conclusions, open_items
```

`independence` 包含：

```text
developer_organizations, vv_executor, reviewer
```

执行者和审核者各包含：

```text
name, role, organization, independent
```

两人必须不同名、均声明 `independent=true`，且组织均不属于开发组织。`activities` 至少包含 `code_verification`、`solution_verification`、`validation` 三种类型。

每项活动使用 `VV-NNN`，包含：

```text
id, type, title, requirement_ids, test_ids, method, acceptance,
observed, uncertainty, result, evidence_ids, deviations, limitations
```

按活动类型还必须提供：

- `code_verification`：`reference_solution`
- `solution_verification`：`convergence_study`、`observed_order`
- `validation`：`benchmark_source`、`applicability_domain`、`uncertainty`、`error_metrics`、`trends`

`error_metrics` 和 `trends` 必须非空。活动结果与证据结果均须为 `passed`；每项活动必须关联需求或测试。最终人工批准人不得是执行者、审核者或开发组织成员。

`conclusions` 包含：

```text
overall, limitations, residual_risk
```

## 软件发布：release

顶层字段：

```text
schema_version, release_id, version, release_scope, source_revision,
configuration, sbom, reproducibility, rollback,
known_limitations, open_items
```

`release_id` 使用 `REL-NNN`；`version` 必须是语义版本，例如 `1.0.0`。`source_revision` 必须与 implementation 阶段一致。`release_scope` 中每个路径必须存在。

`configuration` 包含：

```text
compiler, os, mpi, dependencies, container_images
```

`sbom` 包含：

```text
format, path, evidence_id
```

`path` 必须存在，证据必须为 `passed`。

`reproducibility` 包含：

```text
instructions, verified, evidence_ids
```

`rollback` 包含：

```text
procedure, verified, evidence_ids
```

二者都必须 `verified=true`，且引用 `passed` 证据。门禁要求 `REL --contains-->` 覆盖全部需求与模块。发布门禁完整递归通过后才能运行 `manifest`。

## 追溯模型

文件：`.nuclear-dev/traceability.json`

节点只包含：

```json
{"id": "REQ-001", "kind": "requirement", "title": "标题"}
```

`kind` 只能是：

```text
requirement, design, module, test, vv, release
```

允许关系：

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

阶段产物中的 ID、标题和关联字段必须与追溯语义一致。只更新摘要而漏掉节点或关系会被门禁阻断。

## 证据

证据必须使用 CLI 登记，不得手工猜 ID 或篡改索引：

```bash
python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> evidence add <项目内路径> \
  --kind <类型> --producer <真实生产者> \
  --command <实际命令或可审计操作> \
  --result <passed|failed|observed|not_applicable> --json
```

从 JSON 的 `evidence.id` 读取 `EVID-NNN`。证据文件必须位于项目内；同一路径不能重复登记。失败结果是有效记录，不能改成 `passed`。

## 人工批准

批准路径为 `.nuclear-dev/approvals/<stage>.json`。每阶段门禁要求真实人工批准，字段包括：

```text
stage, approver, decision, date, scope, artifact_sha256, statement
```

`approver` 包含：

```text
name, role, organization, actor_type
```

`actor_type` 必须为 `human`，可附 `credential`；顶层可附 `signature`。`scope` 相对于 `.nuclear-dev`，必须包含当前阶段产物；`artifact_sha256` 必须覆盖 `scope` 中全部文件的真实 SHA-256。任何产物变化都会使旧批准失效。

Agent、Skill、安装器和 CLI 都不创建、修改或推断批准文件。没有真实人工签署时，门禁必须失败并停止。
