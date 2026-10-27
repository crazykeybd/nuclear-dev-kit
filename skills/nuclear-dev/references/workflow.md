# 七阶段受控工作流

## 状态模型

阶段顺序固定为：

```text
plan -> requirements -> design -> implementation -> test -> vv -> release
```

统一使用以下命令，且 `--root` 必须放在子命令之前：

```bash
python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> status --json
python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> gate <阶段> --json
python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> gate <阶段> --no-dependencies --json
python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> validate --json
```

`status` 对每个阶段只评估当前产物，不递归检查依赖；即使有阻断也返回 `0`。`gate` 默认递归检查全部前置阶段，前置产物缺失同样阻断；阶段门禁失败返回 `1`。`validate` 检查已存在产物的 Schema、证据哈希、追溯和批准，失败返回 `1`。参数错误及工具错误返回 `2`。

## 通用阶段循环

每个阶段严格执行以下循环：

1. **检查**：运行 `status --json` 和目标阶段递归 `gate --json`。记录实际错误，不把空文件当成已完成。
2. **读取**：若阶段 JSON 已存在，读取并保留已有字段和人工内容；若不存在，按 `artifact-schema.md` 创建符合 Schema 的候选结构。
3. **起草**：把需求、假设、适用范围、限制、验证方法与未决问题写清楚。未知内容进入 `open_items`，不得填入占位字符串伪装完成。
4. **执行**：完成真实工程活动，例如构建、运行测试、执行基准算例或做误差分析。保留可复查的原始记录。
5. **登记证据**：证据文件放在项目内，执行：

   ```bash
   python3 <SKILL_DIR>/scripts/nuclearctl.py --root <项目> evidence add <项目内路径> \
     --kind <类型> --producer <姓名或组织> \
     --command <实际命令或操作> --result <passed|failed|observed|not_applicable> --json
   ```

   从 JSON 的 `evidence.id` 读取实际 `EVID-xxx`。不要复用已登记路径，不要猜测编号。证据内容变化后，必须重新登记新文件或由人员处理索引；旧哈希会阻断。
6. **追溯**：更新 `.nuclear-dev/traceability.json` 的 `nodes` 和 `links`，保持双向语义一致。
7. **复核**：运行 `validate --json`，再运行目标阶段递归 `gate --json`。处理真实错误，不用删减门禁规则绕过。
8. **停止或交接**：需要人工批准的阶段，在产物稳定后停止，明确列出待批准产物及 SHA-256 来源，交由真实人员独立签署。绝不创建、编辑或推断批准文件。

## 阶段要点

### 软件策划

明确安全分级及依据、V&V 等级及依据、适用标准、工具鉴定、人员资格、配置管理、开放项。至少一个标准状态为 `applicable`；独立 V&V 必须启用；人员必须 `qualified` 且附证据；工具不能为 `pending`；`accepted` 开放项仍阻断，必须为 `closed`。

### 需求分析

每条需求写明来源、理由、安全等级、类别、验证方法、是否需要确认、可量化验收准则。验收准则必须有方法和证据类型。所有需求最终都要被设计分配、测试验证；要求确认的需求还要被 V&V 活动覆盖。

### 软件设计

架构组件不能为空；至少有一个数学模型，完整描述方程、假设、适用范围、离散化、稳定性、守恒和误差分析。每个需求通过 `allocated_to` 分配到一个或多个设计项，设计项中的 `requirements` 必须与追溯一致。

### 编码实现

模块路径必须真实存在；源码工作区必须干净；构建证据必须为 `passed`。每个设计项必须通过 `implemented_by` 映射到模块，模块的 `design_ids` 必须对应。

### 软件测试

至少覆盖 `unit`、`model`、`system` 三种等级，以及 `conservation`、`boundary`、`negative` 三类关注点。测试和回归结果必须 `passed`，引用证据必须 `passed`。每个模块必须有 `exercises`，每条需求必须有 `verifies`。

### 验证与确认

至少有 `code_verification`、`solution_verification`、`validation` 三类活动。执行者与审核者必须是不同人员，均声明 `independent=true`，且组织不在开发组织列表。代码验证要有 `reference_solution`；解的验证要有 `convergence_study` 与 `observed_order`；确认要有 `benchmark_source`、`applicability_domain`、`uncertainty`、非空 `error_metrics` 和非空 `trends`。最终批准人不得是执行者、审核者或开发组织成员。

### 软件发布

版本必须是语义版本；源码 revision 与实现阶段一致；发布范围及 SBOM 文件必须存在；SBOM 证据必须 `passed`；复现性与回滚均须 `verified=true` 且引用 `passed` 证据。release 门禁递归通过后才能生成确定性配置清单。

## 证据纪律

- `producer` 是真实执行者，`command` 是可复现命令或可审计操作说明。
- `result` 只反映实际结果。失败证据是有价值的诊断记录，不能为了通过而改成 `passed`。
- 日志应包含时间、环境、版本、输入、退出码和摘要；大文件可保存摘要与原始文件指针，但所指文件必须存在。
- 证据文件不得位于项目外，也不得通过修改索引手工篡改哈希。
- 批准前若产物发生变化，旧批准自动失效；重新签署必须由人员完成。

## 失败处置

- `status` 为阻断：完成当前阶段或关闭开放项。
- 前置阶段阻断：回到最早失败阶段，不跳阶段。
- 证据哈希不匹配：查明变化，保留新证据并按真实结果重新登记，不能手改旧 SHA。
- 人工批准缺失或范围不符：停止并请求有权限人员独立审查。
- 测试失败：保留失败证据，修复问题后重新执行，登记新的可审计记录。
- 工具/参数错误：修正调用方式；不要把退出码 `2` 当作门禁未完成。
