# A2A 面（远程 V&V）

本文件描述 `nuclear-dev-bot` 的 A2A 客户端与协议画像。威胁与控制项见 [threat-model.md](threat-model.md)。

> **注意**：本项目实现的是自有画像 `nuclear-a2a/1`，**不是 A2A 规范的一致性实现**。与上游规范的逐节对照、已核对项与未核对项见 [a2a-coverage.md](a2a-coverage.md)。在补齐该文件列出的差异之前，不得对外声称"兼容 A2A"。

## 协议画像

- 画像标识：`nuclear-a2a/1`
- 方法：`message/send`、`tasks/get`、`tasks/cancel`
- 非流式；agent card 必须声明 `streaming: false`、`pushNotifications: false`
- JSON-RPC 2.0 over HTTP(S)，请求用 HMAC-SHA256 签名
- `spec_revision` **必须由部署方提供**，不能是 `unpinned`。本包不硬编码上游规范版本号；首次部署时把规范来源 URL、获取日期与 SHA-256 或 commit 记录到本节，再写入配置。

> 当前未记录具体上游修订。接入前必须补齐，否则 `load_config` 会拒绝启动。

## 角色

| 角色 | 职责 |
|---|---|
| `dev` | 生成投影包、双人特批校验、一次性令牌、外发、查询任务 |
| `vv` | 接收委托、产出报告与证据包（M5 实现） |

## 配置

`a2a-config.json`：

```json
{
  "schema_version": 1,
  "agent": {
    "agent_id": "dev-org",
    "organization": "开发组织",
    "spec_revision": "sha256:<规范原文或提交>"
  },
  "peers": {
    "vv-org": {
      "agent_id": "vv-org",
      "organization": "示例 V&V 组织",
      "endpoint": "https://vv.example/a2a",
      "card_url": "https://vv.example/.well-known/agent-card.json",
      "ca_file": "/etc/ssl/vv-ca.pem",
      "transfer_root": "/mnt/vv-exchange"
    }
  }
}
```

约束：

- 非 loopback 必须 `https`；明文 `http` 只允许 loopback。
- endpoint 不得包含凭据、查询或片段。
- `card_url` 省略时由 endpoint 推导。
- `transfer_root` 必须位于项目目录之外。

密钥文件格式、轮换与权限见 [threat-model.md](threat-model.md) 的 T4。

## 导出策略

`.nuclear-dev/a2a/export-policy.json`：

```json
{
  "schema_version": 1,
  "default": "deny",
  "recipients": {
    "vv-org": {
      "organization": "示例 V&V 组织",
      "max_class": "C2",
      "projections": ["requirements", "test_summary", "vv_scope"],
      "allow_c3_raw": false,
      "scope_label": "高完整性等级 A"
    }
  }
}
```

- `default` 只能是 `deny`。
- 未配置策略文件时，所有导出被拒绝。
- C3 原始文件要求 `max_class` 为 `C3` 且 `allow_c3_raw` 为 `true`。
- 策略按接收方索引，不是全局开关。

可选分类附录 `.nuclear-dev/a2a/classification.json`：

```json
{
  "schema_version": 1,
  "entries": [
    {"path": "src/**", "class": "C3", "transferable": true},
    {"path": "benchmark/data.csv", "class": "C3", "transferable": false}
  ]
}
```

`transferable: false` 优先于任何特批：即使 EXP 齐全，导出也会被拒绝。

## 投影包

默认输出到 `.nuclear-dev/a2a/outbox/<bundle_id>/`。

| 投影 | 输出 | 包含 | 明确排除 |
|---|---|---|---|
| `requirements` | `requirements.json` | 需求陈述、验收准则、验证方法 | 理由、安全等级、来源、接口、状态 |
| `design_summary` | `design-summary.md` | 组件与模型名称、适用范围、假设 | 方程、离散格式、稳定性、守恒、误差分析 |
| `test_summary` | `test-summary.json` | 测试等级、类别、结果、证据数量 | 步骤、实际记录、证据 ID |
| `vv_scope` | `vv-scope.json` | 需确认的需求、必需活动类型、模型引用 | 基准题数据、参考解实现 |

`manifest.json` 记录每个输出的分类、SHA-256、大小与来源产物哈希，并带 `digest`。`verify_bundle` 会重算摘要、逐文件校验，并拒绝清单外文件。

## 双人特批（C3 原始文件）

`.nuclear-dev/a2a/export-approvals/EXP-*.json`：

```json
{
  "schema_version": 1,
  "id": "EXP-001",
  "purpose": "白盒代码验证",
  "recipient": {"agent_id": "vv-org", "organization": "示例 V&V 组织"},
  "expires_at": "2026-11-02T00:00:00Z",
  "files": [{"path": "src/solver.py", "sha256": "<64 hex>", "class": "C3"}],
  "approvers": [
    {"name": "张三", "role": "data_owner", "organization": "开发组织", "actor_type": "human", "signed_at": "..."},
    {"name": "李四", "role": "security_officer", "organization": "安全组织", "actor_type": "human", "signed_at": "..."}
  ],
  "statement": "同意在约定用途范围内导出。"
}
```

校验规则：

- 两名批准人，姓名不同、组织不同、`actor_type` 必须为 `human`；
- `signed_at` 不得在未来（允许 5 分钟偏差）；
- 未过期；文件存在且哈希匹配；分类必须为 C3 且可转让；
- 接收方与策略组织必须一致。

**本包不提供创建 EXP 的命令或工具。**

## 一次性令牌

```bash
python3 <SKILL_DIR>/scripts/nucleara2a.py --project <项目> authorize \
  --bundle <投影包目录> --approver <姓名> --ttl 15m
```

- 需要交互终端：`stdin` 与 `stdout` **同时**是 TTY 才继续；非交互调用一律拒绝。
- 终端上显示接收方、摘要、文件数与是否含 C3，必须输入 `yes` 才生成。
- 令牌绑定 `bundle_digest`、接收方、分类上限与有效期；消费时原子标记 `used_at`。
- 复用、过期、摘要不符、接收方不符一律拒绝。

> Windows 上 `NUL` 的 `isatty()` 返回 `True`，所以只检查 stdin 不够；必须同时检查 stdout。

## 命令

全局参数放在子命令之前：

```bash
python3 <SKILL_DIR>/scripts/nucleara2a.py --project <项目> --json plan \
  --recipient vv-org [--projection requirements] [--raw src/solver.py]

python3 ... authorize --bundle <目录> --approver <姓名> [--ttl 15m]
python3 ... stage --config <配置> --keys <密钥> --recipient vv-org --bundle <目录>
python3 ... send  --config <配置> --keys <密钥> --recipient vv-org \
  --bundle <目录> --token AUTH-... [--transfer-ref <引用>]
python3 ... status --config <配置> --keys <密钥> --recipient vv-org --task T-001
python3 ... cancel --config <配置> --keys <密钥> --recipient vv-org --task T-001
python3 ... policy-template
```

- `plan` 只生成投影包，不外发。
- `stage` 把投影包复制到 `transfer_root` 并校验；目标已存在时拒绝覆盖。
- `send` 消费令牌、拉取 agent card、校验带外包摘要后发送；C3 包额外要求 TTY 确认。
- `status` / `cancel` 使用同一套签名。

## MCP 发送（仅 C2）

服务端同时提供 `--allow-write`、`--a2a-config`、`--a2a-keys` 时，`nuclear_a2a_send` 工具出现：

- 参数：`recipient`、`bundle`（项目内相对路径）、`token`、可选 `transfer_ref`；
- **拒绝任何包含 C3 原始文件的投影包**，C3 只能从 CLI 发送；
- 仍然消费一次性令牌；没有令牌就无法发送；
- 不生成令牌，也不修改批准。

## 服务端（V&V 方）

```bash
python3 <SKILL_DIR>/scripts/nucleara2a.py --project <V&V 项目> serve \
  --organization "示例 V&V 组织" --spec-revision <锁定修订> --keys <keys.json> \
  [--agent-id vv-org] [--bind 127.0.0.1] [--port 8765] \
  [--tls-cert <证书> --tls-key <私钥>] [--tls-client-ca <CA>] [--trust-proxy-tls] \
  [--transfer-root <带外目录>] [--rate-per-minute 10] [--rate-burst 20]
```

启动规则：

- 默认绑定 `127.0.0.1`；非 loopback 必须提供 `--tls-cert` 与 `--tls-key`。
- `--trust-proxy-tls` 只允许 loopback 绑定；代理必须注入 `X-Forwarded-Proto: https`。
- `--spec-revision` 不能是 `unpinned`。

端点：

| 路径 | 方法 | 说明 |
|---|---|---|
| `/.well-known/agent-card.json` | GET | agent card |
| `/a2a` | POST | JSON-RPC（`message/send`、`tasks/get`、`tasks/cancel`） |

入站控制：

- 必须带 `Content-Length` 与 `Content-Type: application/json`；超过 4 MiB 返回 413；不支持 chunked。
- HMAC 校验失败统一 401；超过每对端限流返回 429。
- `file` part 禁止内联字节；`transferId` 不得包含绝对路径或 `..`。
- 配置 `--transfer-root` 时逐个校验文件大小与摘要：不符返回 400，缺失则任务进入 `input-required`。
- 请求写入 `.nuclear-dev/a2a/inbox/<task-id>/request.json`；任务账本写入 `.nuclear-dev/a2a/tasks.json`。

隔离断言（可逐条验证）：

1. 服务端写入范围仅限 `<项目>/.nuclear-dev/a2a/` 之下；不写项目源码，不写批准目录。
2. 对端只能读取自己提交的任务；任务 ID 与他人不匹配时按不存在处理。
3. 带外文件只能取自 `--transfer-root` 指定目录；路径含绝对路径或 `..` 一律拒绝。
4. 越界请求一律拒绝并记录，不降级为部分执行。

这四条是"隔离"的可验证定义；实现变更后必须逐条复核，不得只看测试是否通过。

任务状态：`submitted` / `working` / `input-required` / `completed` / `failed` / `canceled`。对端只能读取自己提交的任务。

运维命令：

```bash
python3 ... task list
python3 ... task show --id <任务>
python3 ... task update --id <任务> --state working|input-required|completed|failed|canceled --note "..."
python3 ... task artifact --id <任务> --path <产物文件> --transfer-root <带外目录> [--classification C2|C3]
```

`task artifact` 把产物复制到 `<transfer_root>/<task-id>/<name>`，计算摘要并登记；对端通过 `tasks/get` 拿到 `transferId` 列表，再从带外通道取回。

服务端不执行 V&V 本身：它只接收委托、记录任务与登记产物。V&V 结论仍由人完成并签署。

## 审计

- `a2a_send` 写 `intent` 与 `result` 两条记录；`intent` 失败即中止发送。
- 审计记录包含 `bundle_digest`、接收方、文件数，不含文件内容与密钥。

## 已知限制

- HMAC 是对称的，无不可否认性；密钥泄露即完全冒充。
- 一次性令牌是流程控制，不是密码学边界；同机同用户的 Agent 理论上可调用生成命令（TTY 检查主要挡自动化）。
- 响应不做签名，依赖 TLS 保证完整性。
- 不支持流式、push notifications 与 chunked 请求体。
- 不支持从对端提供的任意 URL 拉取文件；字节一律走带外通道。
- 服务端不执行 V&V，也不自动把对端报告登记为证据；登记必须由人工确认。
- 第三方 A2A 实现需要适配层；当前画像只保证本包两端互通。
