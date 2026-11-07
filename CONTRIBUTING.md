# 参与本仓库

本仓库的主产物是一套**受控研发门禁**。贡献它的第一原则不是"加功能"，而是**不让门禁变弱、不让文档与内核走散**。

## 三条不可谈判的约束

1. **`skills/nuclear-dev/scripts/nuclearlib.py` 是判定规则的唯一事实来源。** 所有 Skill、MCP、A2A、
   面板与智能体都调用它。不要复制、改写或"裁剪"判定逻辑；适配层只翻译，不判定。
2. **不存在批准通道。** 任何 helper、工具、参数、示例都不得生成、修改、推断或放宽
   `.nuclear-dev/approvals/*.json`。批准只能由具备权限的人员在系统之外独立完成。
3. **离线、确定、只用标准库（Python 3.7.3+）。** 不新增第三方依赖，不联网跑测试，输出字节稳定。

## 改一处之前

先跑一遍基线，确认失败不是你引入的：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 tools/check_docs.py
python3 tools/gen_catalog.py --check
python3 tools/check_hosts.py
python3 tools/check_nuclear_dev_agent.py
```

改完再跑一遍。**提交前这五条必须全绿**，CI 跑的也是它们。

## 常见改动落在哪

| 你要改的东西 | 改哪里 | 别忘了 |
|---|---|---|
| 门禁规则、Schema | `nuclearlib.py` | 进位 `SCHEMA_VERSION`；同步 `references/artifact-schema.md`；补正向与负向用例 |
| CLI 子命令 | `nuclearctl.py` | 退出码保持 `0/1/2` 三态；`--json` 与人类可读两条路都要能看 |
| 协议适配（MCP/A2A/轨迹） | `nuclearproto/` | 适配层不许出现判定逻辑；`nuclearproto/trace.py` 的三条硬保证不许破 |
| 新增/修改 Skill | `skills/<name>/SKILL.md` | 正文有 8 KB 硬上限；跑 `tools/gen_catalog.py` 重新生成 `catalog.json`；同步两份 `references/host-compatibility.md` 里的字节数表格 |
| 阶段集合 | `nuclearlib.STAGES` 及其下游 | Python 内核、`catalog.json`、`nuclear-dev-agent/src/nuclear/types.ts`、面板文案必须一致 |
| 文档 | `README.md`、`INSTALL.md`、`docs/`、`skills/*/references/` | `tools/check_docs.py` 会校验文档里出现的 `nuclear_*` 名字必须真实存在 |
| 智能体 | `nuclear-dev-agent/` | 先在 `FORK.md` 记来源与改动；TypeScript 侧另跑 `pnpm typecheck && pnpm test` |

## 加一个阶段要动的地方

阶段是**全序**的，加一个阶段等于改门禁契约，按顺序改完再提交：

1. `nuclearlib.STAGES`、`STAGE_LABELS`、`STAGE_ARTIFACTS`、`STAGE_SKILLS`，以及 `STAGE_SCHEMAS`；
2. `stage_gate` 里该阶段的专属检查（`_stage_specific`）与跨阶段追溯要求；
3. `skills/nuclear-<阶段>/SKILL.md`（frontmatter 的 `name` 必须与目录同名）；
4. `nuclear-dev-agent/src/nuclear/types.ts` 与 `agents.ts` 的阶段表，以及 `prompts/stage/<阶段>.md`；
5. `python3 tools/gen_catalog.py` 重新生成 `catalog.json`；补 `tests/support.py` 的夹具；
6. 文档：`README.md` 的阶段表、`references/artifact-schema.md`、`references/workflow.md`。

不想动契约、只想加个检查？那多半不是新阶段，而是现有阶段的 `_stage_specific` 里多一条判据。

## 提交与 Pull Request

- 提交信息用约定式前缀：`feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`chore:`。
- 一个 PR 只做一件事；顺手改的无关格式请单独提。
- 用仓库的 PR 模板填：做了什么、为什么、怎么验的、有没有碰判定规则。
- 明确写"没做什么"：不确定的、被拒绝的方案、留待后续的口子，都写在 PR 里，别留在脑子里。

## 报告问题

安全或完整性相关的问题（门禁可被绕过、批准可被伪造、轨迹链可被静默改写）请直接用私密渠道联系维护者，
不要在公开 issue 里贴可利用细节。
