# MCP 面

本包提供一个只读的 MCP stdio 服务端，让支持 MCP 的宿主（Claude Code、Codex、Reasonix 及其他 MCP 客户端）调用同一套门禁实现。

服务端代码位于 `skills/nuclear-dev/scripts/nuclearmcp.py`，协议适配层位于 `skills/nuclear-dev/scripts/nuclearproto/`。门禁规则的唯一事实来源仍是 `nuclearlib.py`，适配层不复制任何规则。

## 启动

```bash
python3 <SKILL_DIR>/scripts/nuclearmcp.py --workspace <允许根目录> [--workspace <另一个根目录>] \
  [--allow-write] [--audit-sink <路径或URL>] [--audit-sink-token-file <路径>] \
  [--a2a-config <路径> --a2a-keys <路径>]
```

- `--workspace` 可重复，至少一个。根目录名即 workspace 标识；同名不同路径会被拒绝。
- 默认传输为 stdio；日志只写 stderr，stdout 只输出 JSON-RPC 消息。
- 默认只读：不暴露写入工具，不写项目文件。加 `--allow-write` 才启用写入工具与审计日志。
- `--audit-sink` 可重复；文件必须在 workspace 之外，远端只允许 https（loopback 可 http）。
- `--a2a-config` 与 `--a2a-keys` 必须同时提供，并且需要 `--allow-write`；否则 `nuclear_a2a_send` 不出现。

## 协议

- JSON-RPC 2.0，换行分隔，UTF-8。
- 支持的方法：`initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`、`resources/list`、`resources/templates/list`、`resources/read`、`prompts/list`、`prompts/get`。
- 协议版本：客户端请求 `2025-06-18`、`2025-03-26`、`2024-11-05` 之一时原样回应，否则回落到 `2025-06-18`。

## 工具（全部只读）

| 工具 | 必需参数 | 返回 |
|---|---|---|
| `nuclear_status` | — | 各阶段当前状态 |
| `nuclear_gate` | `stage` | `ok`、`errors`、`exit_code` |
| `nuclear_validate` | — | `errors`、`exit_code` |
| `nuclear_read_artifact` | `stage` | `exists`、`sha256`、`artifact` |
| `nuclear_schema` | `stage` | 阶段产物 JSON Schema |
| `nuclear_evidence_list` | — | `count`、`evidence` |

可选参数：

- `workspace`：workspace 标识。只有一个 workspace 时可省略。
- `project`：workspace 内的项目相对路径，默认 `.`。
- `include_dependencies`：仅 `nuclear_gate` 使用，默认 `true`。

不存在的写入工具：`nuclear_init`、`nuclear_evidence_add`、`nuclear_manifest` 仅在 `--allow-write` 时暴露；任何形式的 `approve`、`sign` 永不提供。

每个判定响应都带 `rules_version`、`kit_sha256`、`schema_version`、`workspace`、`project_path`。

## 写入工具（仅 `--allow-write`）

| 工具 | 必需参数 | 说明 |
|---|---|---|
| `nuclear_init` | — | 初始化 `.nuclear-dev` 工作区；可选 `name`、`id` |
| `nuclear_evidence_add` | `path`、`kind`、`producer`、`command`、`result` | 登记项目内证据，返回 `evidence.id` |
| `nuclear_manifest` | `version` | 发布门禁通过后生成配置清单；可选 `force` |
| `nuclear_a2a_send` | `recipient`、`bundle`、`token` | 发送 C2 投影包；需要一次性令牌；C3 原始文件拒绝 |

`nuclear_a2a_send` 仅在同时提供 `--allow-write`、`--a2a-config`、`--a2a-keys` 时出现。它：

- 只接受项目内相对路径的投影包；
- 拒绝包含 `raw_files` 的 C3 投影包（C3 只能从 CLI 发送）；
- 消费一次性令牌后发送；令牌复用、过期、摘要或接收方不符一律拒绝；
- 不生成令牌，也不修改批准。

写入约束：

- `nuclear_evidence_add` 的 `path` 必须是**项目内相对路径**。绝对路径与越出项目的路径一律拒绝。
- 写入工具只写 `.nuclear-dev/`；不会修改项目源码。
- 写入工具不产生、不修改、不推断批准文件。
- 写入失败返回 `isError: true`，不改变已有产物。

## 审计日志

启用 `--allow-write` 后，工具调用写入 `.nuclear-dev/audit/<UTC 日期>.jsonl`，并用 `.nuclear-dev/audit/state.json` 维护链头。

```json
{"schema_version":1,"seq":42,"timestamp":"…","tool":"nuclear_gate","phase":"result",
 "actor":"claude-code","workspace":"example","project_path":"…","arguments_sha256":"…",
 "ok":true,"is_error":false,"exit_code":0,"duration_ms":3,
 "rules_version":"0.1.0","kit_sha256":"…","prev_sha256":"…","sha256":"…"}
```

- `seq` 跨日单调递增；`prev_sha256` 指向上一条的 `sha256`；首条为 64 个 0。
- 变更类工具（`nuclear_init`、`nuclear_evidence_add`、`nuclear_manifest`）先写 `phase=intent` 再执行，成功后写 `phase=result`；只读工具只写 `result`。
- 只记录参数哈希，不记录原文；字符串经 JSON 序列化，换行自动转义。
- 跨进程锁：POSIX `fcntl.flock`，Windows `msvcrt.locking`。
- 审计是线索，不是证据，不参与门禁判定；`validate` 不检查它。

**失败语义**：

- 变更类工具：`intent` 写入失败 → **操作中止**；`result` 写入失败 → 返回错误，明确说明“操作已执行但结果审计缺失”。
- 只读工具：审计失败降级为 stderr 警告，不改变返回结果。

**外部出口**：

```bash
--audit-sink /var/log/nuclear/dev-audit.jsonl    # 文件，必须位于 workspace 之外
--audit-sink https://logs.example.com/audit      # HTTPS 推送
--audit-sink-token-file /etc/nuclear/sink.token  # Bearer 令牌
```

- file sink 位于 workspace 内时拒绝启动。
- 远端 `http` 仅允许 loopback；其他一律要求 `https`。
- sink 投递失败按上面的失败语义处理。

**查看与校验**：

```bash
python3 <SKILL_DIR>/scripts/nuclearaudit.py --root <项目> head --json
python3 <SKILL_DIR>/scripts/nuclearaudit.py --root <项目> verify --json
```

- `head` 输出链头与建议写入批准 `statement` 的片段，**不写批准文件**。
- `verify` 检查记录哈希、序号连续性、链断裂与状态文件尾部一致性；尾部截断会被状态文件发现。

**局限**：状态文件与日志同目录，能防误删与部分篡改，不能防整链重写。生产环境应把 `--audit-sink` 指向不同主机。

## 返回契约

| 情况 | 表现 |
|---|---|
| 门禁通过 | `ok: true`，`exit_code: 0`，`isError` 缺省 |
| 门禁阻断 | `ok: false`，`errors: [...]`，`exit_code: 1`，**`isError` 不为 true** |
| 参数错误、路径越界、内部异常 | `isError: true`，`content` 内含 `ok: false` 与 `error` |
| 未知工具 | JSON-RPC 错误 `-32602` |

门禁阻断是有效判定，不是工具故障。宿主不得把它当噪声重试。

## 资源

静态资源：

| URI | 内容 |
|---|---|
| `nuclear://workflow` | 七阶段工作流规则 |
| `nuclear://kit/version` | 工具包版本、规则版本、规则哈希、阶段列表 |
| `nuclear://schema/<stage>` | 阶段产物 Schema |

资源模板：

| 模板 | 内容 |
|---|---|
| `nuclear://project/{workspace}/{project}/stages/{stage}` | 阶段产物 |
| `nuclear://project/{workspace}/{project}/traceability` | 追溯图 |
| `nuclear://project/{workspace}/{project}/evidence` | 证据索引 |

资源不存在或越出 workspace 时返回 JSON-RPC 错误 `-32002`。

## 提示词

`nuclear-dev` 与七个阶段 Skill 全部暴露为 MCP Prompt。`prompts/get` 在运行时读取对应 `SKILL.md`，去掉 YAML frontmatter 后返回正文。

这样工程指令只有一个来源：修改 `SKILL.md` 即同时改变 Skill 面与 MCP 面，不存在第二份副本。

## instructions

`initialize` 返回的 `instructions` 固定包含四条纪律：

1. 修改阶段产物前先调用 `nuclear_gate`；
2. 门禁阻断必须原样报告，不得重试到“看起来通过”；
3. 本服务没有 `approve` 工具，也不会生成批准文件；
4. 本服务不提供批准、授权记忆、凭据读写、删除数据与修改宿主配置。

这四条对不支持 Skill 机制的宿主是唯一可得的工程规则。

## 安全边界

- 允许根目录只由启动参数给定；调用方只能传相对路径，`..`、绝对路径、符号链接跳转全部拒绝。
- 默认只读；写入必须由启动方显式加 `--allow-write`。
- 写入工具只写 `.nuclear-dev/`；证据路径必须是项目内相对路径。
- 每个判定响应带 `rules_version`、`kit_sha256`、`schema_version`，便于审计归因。
- 门禁通过不等同监管批准或真实工程合规。

## 不提供的能力

以下能力**不在任何版本中出现**，不要尝试调用、组合或推断：

| 能力 | 状态 |
|---|---|
| 批准、签署、放行 | 永不存在；批准必须在系统之外由有权限的人完成 |
| 授权记忆（"以后都放行"） | 永不存在；常驻指令不构成对任何一次具体门禁的通过 |
| 凭据读写、令牌生成 | 不存在；A2A 令牌只能由人在交互终端生成 |
| 删除产物、证据或审计 | 不存在；删除必须由人直接操作文件系统 |
| 修改宿主配置 | 不存在；配置改动一律经由 `register.py` 由用户确认执行 |

写清楚"不做什么"与写清楚"做什么"同样重要：调用方据此可以判定"这一步不该由 bot 完成"，而不是反复尝试。

## 间接调用

若将来引入任何间接调用入口（批量执行、组合工具、代理转发），**间接调用不得绕过直接调用的任何一项检查**：参数校验、路径约束、门禁判定、审计记录、批准禁令全部逐项适用。

理由：绕过点一旦存在，攻击者只需找到最短路径；审计链也会因入口不同而分叉。当前版本不提供间接调用入口，此条作为约束保留。

## 一致性要求

MCP 判定必须与 `nuclearctl.py` 逐字节一致。`tests/test_mcp.py` 包含 CLI 与 MCP 的对照断言；修改任一侧都必须保持该测试通过。
