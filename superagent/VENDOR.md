# 来源与更新说明（vendored）

本目录是上游 `dsh-superagent` 原型代码的**只读副本**，供本项目把核能门禁工作流接进
DeepSeek Harness 的 superagent 形态时使用。

| 项 | 值 |
|---|---|
| 上游仓库 | https://github.com/deepseek-ai/dsh-superagent-prototype |
| 上游提交 | `8c32a9dc5d72c033816c6a8110b37f40cf94fba4`（main） |
| 复制日期 | 2026-11-05 |
| 许可证 | MIT，见同目录 `LICENSE`（版权归 DeepSeek Harness Team） |
| 上游文档 | 同目录 `README.md`、`SETUP.md`、`docs/` |

## 本仓库做了什么

**没有修改任何上游文件。** 核能流程的接入全部放在上游目录之外：

- 十个 `nuclear-*` Skill 仍在仓库根的 `skills/`，是唯一事实来源；
- 通过 `skills/nuclear-setup/scripts/install.py dsh --scope project` 把它们装进
  Ticket 工作目录（见 [../docs/superagent.md](../docs/superagent.md)），
  由 DSH 的 `@deepseek-ai/dsh-skill-filesystem` 自动发现；
- 门禁判定仍由 `skills/nuclear-dev/scripts/nuclearlib.py` 提供，superagent 侧不做任何规则复制。

这样上游更新时可以整目录替换，不会产生补丁冲突。

## 复制范围

已复制：`src/`、`lib/`、`prompts/`、`skills/`、`locale/`、`scripts/`、`examples/`、`docs/`、
`tests/`、`package.json`、`pnpm-lock.yaml`、`tsconfig.json`、`tsdown.config.ts`、
`vitest.config.ts`、`cordis.patch.yml`、`LICENSE`、`README.md`、`SETUP.md`。

未复制：`node_modules/`、`.artifacts/`（两者由上游 `.gitignore` 忽略，属本机产物）。

`lib/` 是上游的构建产物，按上游约定**不入库**（同样被 `.gitignore` 忽略）。部署前须在
本目录执行 `pnpm install && pnpm build`，见 `docs/006-deployment.md`。

## 如何升级

```bash
git clone https://github.com/deepseek-ai/dsh-superagent-prototype /tmp/upstream
cd /tmp/upstream && git checkout <新提交>
rsync -a --delete \
  --exclude node_modules --exclude .artifacts --exclude lib \
  /tmp/upstream/ <本包>/superagent/
```

然后把 `superagent/VENDOR.md`（本文件）里的「上游提交」和「复制日期」改成新值——本文件
不属于上游，`--delete` 会把它删掉，改完记得从版本库恢复。回归测试
`tests/test_superagent_vendor.py` 会校验本表与工作区一致。

## 上游注意事项（照抄，供判断风险）

上游 README 首段写明：这是**研究原型，非官方产品**，可能仍有 bug，工程实践不一定一致，
用于自有环境前须自行审查与适配。本仓库只做部署集成，不对上游行为作任何担保。
