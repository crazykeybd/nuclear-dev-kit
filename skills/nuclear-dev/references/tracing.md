# 门禁运行轨迹标准 v1

门禁今天是"当时说了算"的：跑一次 `gate`，通过或不通过，然后这条输出就没了。审计要问的往往是另一个
问题——**当时那次判定看到的到底是哪些产物、内核原话是什么、换台机器重跑还算不算**。轨迹回答的就是这个。

轨迹是**线索，不是证据**：它不参与门禁判定，不改写结论，也不替代阶段产物、证据登记或人工批准。

## 三条硬保证

1. **关掉就是空操作**：默认不写轨迹。未启用时不建目录、不写文件，`gate` 的行为与没有本特性时逐字一致。
2. **错误不越界**：写轨迹的任何失败（磁盘满、目录被占、权限不足）只打印警告，**门禁结论与退出码不变**。
   不许因为"记不下来"就把阻断说成通过，也不许反过来。
3. **导入即安全**：`nuclearproto/trace.py` 可在无任何配置的环境里导入与调用。

## 契约

一次运行一个文件：`.nuclear-dev/traces/<trace_id>.json`。

| 字段 | 含义 |
|---|---|
| `schema_version` | 恒为 `1`；字段不兼容变化时必须进位 |
| `trace_id` | `TRC-<UTC 时间>-<6 位随机十六进制>`；只用文件名安全字符，Windows 也能落盘 |
| `kind` | 这次运行是什么：当前为 `gate` |
| `stage` | 被判定（或被体检）的阶段 |
| `root` | 被判定工作区的绝对路径 |
| `actor` | 谁跑的：默认 `nuclearctl`，可用 `NUCLEAR_DEV_TRACE_ACTOR` 覆盖 |
| `sequence` | 本工作区内的序号，从 1 开始、连续 |
| `prev_record_sha256` | 上一条轨迹的 `record_sha256`；第一条为 64 个 `0` |
| `record_sha256` | 本记录自身的摘要（见下） |
| `started_at` / `finished_at` / `duration_ms` | 起止时间与耗时 |
| `environment` | `kit_version`、`schema_version`、`rules_sha256`、Python 版本与平台 |
| `spans` | span 列表，树状 |
| `verdict` | `{ok, errors}`：门禁/体检的结论与**内核原话**，逐字保留 |
| `artifacts` | 这次判定看过的产物与批准文件：`{stage, path, present, sha256}` |

`record_sha256` = 去掉 `record_sha256` 字段后，按规范 JSON（键排序、无多余空白）求 SHA-256。
因此任何字段被改一个字节，自校验就会失败。

### span

| 字段 | 含义 |
|---|---|
| `span_id` | `S1`、`S1.1`、`S1.2`…，层级写在名字里 |
| `parent_span_id` | 父 span；根为 `null` |
| `name` | 点分语义名：`gate.<阶段>`、`stage.check.<阶段>` |
| `kind` | `gate` 或 `check` |
| `start` / `end` / `duration_ms` | 该 span 的时间 |
| `status` | `ok`，或 `error` 表示这个 span 本身抛了异常 |
| `attributes` | 该 span 的事实；判定内容（`ok`、`errors`）写在这里 |
| `events` | 时间线，如 `gate.evaluated`、`stage.checked`、`artifacts.hashed` |

**阶段自检返回错误不是 span 故障**：内核说"这一阶段不通过"是一次成功的观察，`status` 仍是 `ok`，
错误写在 `attributes.errors` 里。只有轨迹自身出错才会是 `status: error`。

## 链接、校验与偏离

- 同一工作区的轨迹串成一条链：序号连续、每条都指着上一条的摘要。删一条、改一条、插一条都会被发现。
- `trace verify` 校验链：`ok` 只表示**链自洽**（序号、摘要、前序链接都对得上）。
- 产物或批准文件在轨迹写下之后变了，报为 **偏离（`drift`）**，`state` 为 `changed` 或 `removed`。
  偏离**不影响 `ok`**：阶段产物本来就是会改的工程对象，改了不等于篡改；它只说明"这条轨迹描述的已经不是
  现在这份产物"，需要重跑一次门禁。批准失效另由 `validate`/`gate` 按产物摘要判定。

## 怎么用

```bash
# 跑一次门禁并把判定记成轨迹
python3 nuclearctl.py --root <项目> gate design --trace --json

# 默认打开（例如装在自动化流水线里）
export NUCLEAR_DEV_TRACE=1
export NUCLEAR_DEV_TRACE_ACTOR="流水线 A"   # 可选

# 看轨迹
python3 nuclearctl.py --root <项目> trace list --limit 20 --json
python3 nuclearctl.py --root <项目> trace show <trace_id> --json
python3 nuclearctl.py --root <项目> trace verify --json

# 一次体检：环境、结构、阶段、轨迹链、审计链
python3 nuclearctl.py --root <项目> doctor --json
```

退出码与内核一致：`0` 通过、`1` 不通过、`2` 参数或工具错误。`doctor` 的 `ok` 表示"这处工作区是完好的"，
不是"七个阶段都通过了"；未开始的阶段只作为进展事实列出。

## 保留与销毁

轨迹是追加式的，不自动删。删掉某条会让链断开，`trace verify` 会报出来——这是有意为之。确实需要腾空间时，
应由人员把"删哪些、为什么、谁批的"记成一次显式的受控决定，而不是让工具悄悄清理。

## 与上游的关系

本标准的取舍参考了 Raven 的 `docs/TRACING_STANDARD_API.md`（"tracing 定标准，应用来采纳"、span 树、
关掉即空操作、错误不越界）。未采纳的部分与理由：

- **内容寻址的离体产物**（把大段 prompt / 工具 IO 另存为 artifact）：门禁一次判定的载荷很小，产物完整性
  已由证据哈希覆盖，多一套寻址只会多一处要维护的一致性；
- **OpenTelemetry 式导出器**：本项目离线运行、只用标准库，不引入传输层；
- **`trace_id` 跨进程父子关系**：门禁是单进程短任务，span 树自足即可。

采纳与拒绝的完整说明见本仓库的 `docs/raven-alignment.md`（该目录是给人读的部署说明，不随 Skill 包分发）。
