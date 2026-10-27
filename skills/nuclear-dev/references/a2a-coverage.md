# A2A 规范覆盖度对照

本文件回答一个问题：**本项目与上游 A2A 规范到底一致到什么程度。**

结论先行：本项目实现的是自有画像 `nuclear-a2a/1`，**不是 A2A 规范的一致性实现**。它在方法名与任务状态上与规范同向，但 agent card、对象模型、认证与绑定要求均未按规范实现。因此**不得对外声称"兼容 A2A"**，只能声称"采用 A2A 风格的方法名的自定义协议"。

## 上游锚点

| 项 | 值 |
|---|---|
| 规范 | Agent2Agent (A2A) Protocol Specification |
| 版本 | 1.0.0（该文档自称 Latest Released Version） |
| 来源 URL | `https://raw.githubusercontent.com/a2aproject/A2A/main/docs/specification.md` |
| 获取日期 | 2026-10-27 |
| 仓库 commit | `415a2e1c025e0b2cf0d1dd0dd49c73317e3b8340`（GitHub Contents API 返回的 blob sha） |
| 文件 SHA-256 | `8af843abb347083d175945c9c3e340a68288fdf3a5eee8b38514fa1a158d7e88` |
| 文件大小 | 157901 字节 |

> 部署时 `spec_revision` 必须写入上面这份锚点（见 [a2a.md](a2a.md)），不得使用 `unpinned`。

## 状态取值

| 取值 | 含义 |
|---|---|
| 覆盖 | 已按规范实现，并有代码证据 |
| 部分 | 同名概念存在，但结构或语义与规范不一致 |
| 偏离 | 有意采用不同设计，且已在本文记录理由 |
| 不适用 | 本项目明确不提供该能力（非流式、无推送等） |
| 未核对 | 尚未逐条比对；**不得当作通过** |

## 逐节对照

| 规范章节 | 状态 | 本项目情况 | 证据 |
|---|---|---|---|
| 1. Introduction | 不适用 | 说明性章节 | — |
| 2. Terminology | 部分 | 沿用 task / artifact / message 词汇，但对象结构自定义 | `a2a.md` |
| 3.1 Core Operations | 部分 | 仅实现 `message/send`、`tasks/get`、`tasks/cancel` 三个方法 | `nuclearproto/a2a_server.py:38` |
| 3.2 Operation Parameter Objects | 未核对 | 请求体为自定义结构，未与规范参数对象逐字段比对 | — |
| 3.3 Operation Semantics | 部分 | `message/send` 创建任务；语义细节未逐条核对 | `nuclearproto/a2a_server.py` |
| 3.4 Multi-Turn Interactions | 部分 | 通过 `input-required` 状态支持等待输入 | `a2a.md` |
| 3.5 Task Update Delivery | 不适用 | 非流式，无 push notification | `a2a_server.py:197` |
| 3.6 Versioning | 偏离 | 用 `spec_revision` 由部署方钉住上游修订，而非协议内协商 | `a2a.md:11` |
| 3.7 Messages and Artifacts | 部分 | 任务账本与产物登记为自定义结构 | `.nuclear-dev/a2a/tasks.json` |
| 4.1 Core Objects | 未覆盖 | 未实现规范的 AgentCard / Task / Message / Part 对象模型 | — |
| 4.2 Streaming Events | 不适用 | 无流式 | `a2a_server.py:197` |
| 4.3 Push Notification Objects | 不适用 | 无推送 | `a2a_server.py:197` |
| 4.4 Agent Discovery Objects | 偏离 | agent card 为自定义字段（见下节） | `a2a_server.py:190` |
| 4.5 Security Objects | 偏离 | 使用 HMAC-SHA256 共享密钥，非规范的安全对象 | `a2a_server.py:198` |
| 4.6 Extensions | 未实现 | 不支持扩展协商 | — |
| 5.1–5.8 Binding Requirements | 未覆盖 | 自定义画像，未声明 JSON-RPC 绑定一致性，字段命名未按规范约定 | — |
| 6.1 Basic Task Execution | 部分 | 有对应流程，未按规范示例逐字段核对 | `a2a.md` |
| 6.2 Streaming Task Execution | 不适用 | 无流式 | — |
| 6.3 Multi-Turn Interaction | 部分 | 见 3.4 | — |
| 6.5 Task Listing and Management | 部分 | 提供 `task list/show/update/artifact` 运维命令，非规范方法 | `a2a.md` |
| 6.6 Push Notification Setup | 不适用 | 无推送 | — |
| 6.7 File Exchange | 部分 | `file` part 禁止内联字节，改用 `transferId` 带外交换 | `a2a.md` |
| 6.8 Structured Data Exchange | 未核对 | — | — |
| 6.9 Authenticated Extended Agent Card | 未实现 | 无扩展 agent card | — |
| 7.1–7.6 Authentication | 偏离 | 未实现 OAuth 2.0 / OIDC；HMAC 为对称密钥，无不可否认性 | `a2a.md`、`threat-model.md` |
| 8. Agent Card | 偏离 | 字段集与规范不同（见下节） | `a2a_server.py:190` |
| 9. JSON-RPC Binding | 部分 | JSON-RPC 2.0 帧正确，但错误码仅用通用码，未实现规范映射表 | `nuclearproto/jsonrpc.py:10-15` |

## agent card 字段差异（已核对）

本项目 `agent_card()` 返回的字段：

```json
{
  "schema_version": 1,
  "agent_id": "...",
  "organization": "...",
  "protocol_profile": "nuclear-a2a/1",
  "spec_revision": "...",
  "capabilities": {"streaming": false, "pushNotifications": false},
  "security": {"scheme": "hmac-sha256"},
  "roles": ["vv"],
  "methods": ["message/send", "tasks/get", "tasks/cancel"]
}
```

规范第 8 章要求的 agent card 至少包含 `protocolVersion`、`name`、`description`、`url`、`version`、`capabilities`、`defaultInputModes`、`defaultOutputModes`、`skills` 等字段。**两者不兼容**：本项目的 card 无法被规范客户端解析。

这是有意的设计取舍：本项目只需要「开发方 ↔ 独立 V&V 方」这一条封闭链路，双方都用本包的客户端与服务端，不需要与第三方 A2A agent 互通。代价是**不能声称兼容 A2A**。

## 若要真正兼容 A2A

需要的最小改动（供未来评估，当前不做）：

1. agent card 补齐规范字段，并保留自定义字段作为扩展；
2. 实现规范的对象模型与字段命名约定（第 4、5 章）；
3. 错误码按规范映射表对齐（第 5.4 节）；
4. 认证改为规范接受的安全方案，或声明为扩展；
5. 通过官方一致性测试或对端互通测试取得证据。

在完成上述工作前，任何"兼容 A2A"的表述都属于**未验证结论**。

## 维护约定

- 上游规范修订后，必须先更新本文顶部的锚点（版本、commit、SHA-256、日期），再逐条复核。
- "未核对"不得写成"覆盖"；没有代码证据的条目一律保持"未核对"。
- 本文与 [a2a.md](a2a.md) 冲突时，以代码与本文表为准，并修正 `a2a.md`。
