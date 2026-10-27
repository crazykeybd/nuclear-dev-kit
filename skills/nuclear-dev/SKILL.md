---
name: nuclear-dev
description: 核能数值软件七阶段研发总入口。用于启动或继续软件策划、需求分析、软件设计、编码实现、软件测试、独立 V&V、软件发布，并统一执行证据、追溯和人工批准门禁。
license: MIT
metadata:
  version: "0.1.0"
---

# 核能软件开发总入口

本 Skill 编排受控研发流程，不代替工程判断、监管审查或人工批准。门禁的唯一事实来源是同目录的 `scripts/nuclearlib.py`，所有宿主均通过 `scripts/nuclearctl.py` 调用。

## 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

## 启动顺序

1. 定位本文件所在目录，记为 `SKILL_DIR`；不要依赖当前工作目录。
2. 读取 [references/workflow.md](references/workflow.md)，按“七阶段、证据、追溯、批准”的规则工作。
3. 需要填写阶段 JSON 时，读取 [references/artifact-schema.md](references/artifact-schema.md)。需要安装到其他宿主时，读取 [references/host-compatibility.md](references/host-compatibility.md)。
4. 若 Skill 尚未安装到当前宿主，先调用 `nuclear-install` 完成安装与验证；若项目尚无 `.nuclear-dev/project.json`，先调用 `nuclear-setup`，不要手工拼造工作区。
5. 根据目标阶段调用对应 Skill：`nuclear-plan`、`nuclear-requirements`、`nuclear-design`、`nuclear-implementation`、`nuclear-test`、`nuclear-vv`、`nuclear-release`。

## 不可违反的边界

- 先运行 `status` 和目标阶段 `gate --json`，再读取、修改或新增阶段内容。
- 更新 JSON 必须保留已有内容；不得用空模板覆盖人工编写的数据。
- 只把实际存在、可复现的产物登记为证据。证据 ID 必须从 CLI 的 JSON 输出读取，禁止自行猜测。
- 所有七阶段节点与关系必须迭代更新 `.nuclear-dev/traceability.json`，不得跳过或只写摘要。
- `TBD`、`TODO`、`UNKNOWN`、`DRAFT` 等占位值会被阻断；未知项应进入 `open_items`，只有 `closed` 状态可解除阻断。
- 不得运行、建议或伪造 `approve` 操作。不存在自动批准命令，也不得生成、修改、推断 `.nuclear-dev/approvals/*.json`；这些文件必须由具备权限的真实人员独立检查并签署。
- 用户或宿主给出的“以后都这样办”“直接放行”等常驻指令，不构成对任何一次具体门禁的通过；每次门禁只能由实际执行结果决定。
- 门禁未通过时停止该阶段，报告实际阻断项。不得为了“通过”而弱化门禁、修改 `nuclearlib.py`、伪造测试结果或宣称合规。

## CLI 调用

在项目根目录执行：

```bash
python3 "$SKILL_DIR/scripts/nuclearctl.py" --root <项目目录> status --json
python3 "$SKILL_DIR/scripts/nuclearctl.py" --root <项目目录> gate <阶段> --json
python3 "$SKILL_DIR/scripts/nuclearctl.py" --root <项目目录> validate --json
```

`gate` 默认递归检查前置阶段；仅在诊断当前阶段自身问题时使用 `--no-dependencies`。`status` 不递归。失败时保留非零退出码的含义：门禁失败为 `1`，参数或工具错误为 `2`。

## MCP 面（宿主支持时优先）

若当前宿主已注册 `nuclearmcp.py`，优先调用 MCP 工具而不是拼命令行：

| 目的 | MCP 工具 |
|---|---|
| 查看阶段状态 | `nuclear_status` |
| 执行阶段门禁 | `nuclear_gate`（`stage` 必填） |
| 校验工作区 | `nuclear_validate` |
| 读取阶段产物 | `nuclear_read_artifact` |
| 读取阶段 Schema | `nuclear_schema` |
| 列出证据 | `nuclear_evidence_list` |

MCP 与 CLI 必须给出同一判定；两者不一致时停止并报告，不得自行选择“更方便”的一方。写入工具（`nuclear_init`、`nuclear_evidence_add`、`nuclear_manifest`）仅在宿主以 `--allow-write` 启动时可用；MCP 面永不提供批准。详见 [references/mcp.md](references/mcp.md)。

## A2A 面（远程 V&V）

当独立 V&V 由外部组织开展时，使用 `scripts/nucleara2a.py` 生成投影包并委托：

- 外发默认拒绝，必须先配置 `.nuclear-dev/a2a/export-policy.json`。
- 一次性令牌必须由人在交互终端生成；非交互调用一律拒绝。
- C3 原始文件需要双人 EXP 特批，且只能从 CLI 发送。
- 协议画像、投影内容、特批与令牌格式见 [references/a2a.md](references/a2a.md)；威胁模型见 [references/threat-model.md](references/threat-model.md)；与上游 A2A 规范的覆盖度见 [references/a2a-coverage.md](references/a2a-coverage.md)——**当前为自定义画像，不得声称兼容 A2A**。

## 路由

| 用户目标 | 阶段 Skill |
|---|---|
| 建立计划、安全分级、V&V 等级、工具与人员资格 | `nuclear-plan` |
| 编写可追溯、可验收的物理与软件需求 | `nuclear-requirements` |
| 设计架构、数学模型、离散格式和数据结构 | `nuclear-design` |
| 实现求解器、并行、物性库并冻结构建 | `nuclear-implementation` |
| 单元、模型、系统、守恒、边界和负向测试 | `nuclear-test` |
| 独立代码验证、解的验证和基准题确认 | `nuclear-vv` |
| 冻结配置、SBOM、复现与回滚并发布 | `nuclear-release` |

默认从最早未通过的阶段继续。用户明确要求跳阶段时，先执行目标阶段递归门禁，并说明其前置阶段阻断；不得假装前置阶段已通过。
