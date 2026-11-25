# process-assets：过程资产库 V5.0 Skill 包

本目录由 [tools/split_process_assets.py](../tools/split_process_assets.py) 从合并导出 `~/Desktop/资产库.md` 确定性重建，包含 **40 个独立 Skill**（39 个业务 + 1 个路由）。它们是核能软件研发各阶段要交付的**文档模板与编制指引**，与 `skills/` 下的七阶段门禁 Skill 互补：

- `skills/nuclear-*`：怎么按受控流程做、门禁怎么判；
- `process-assets/skills/*`：每个阶段要产出哪些正式文档、用什么母版、填什么字段。

> 本包只生成/填写工程文档，不参与门禁判定，不生成人工批准，不伪造测试结果。母版文件（DOCX/XLSX/PPTX）位于原 `过程资产库V5.0` 目录；Skill 记录母版路径与字段结构，Agent 可用 python-docx / openpyxl / python-pptx 按结构生成，无母版时按字段新建。

## 入口

- **路由器**：[process-asset-router](skills/process-asset-router/SKILL.md) — 用户提到阶段/文档类型时先转调它，再分发到具体 Skill。
- **阶段映射**：[STAGE-MAPPING.md](STAGE-MAPPING.md) — p1–p9 到 nuclear-dev-kit 七阶段的映射，以及每阶段推荐的资产 Skill。
- **只读查询**：`python3 process-assets/scripts/assetctl.py stage <阶段> --json` 列出某阶段的资产 Skill；`python3 .../assetctl.py list --json` 列出全部。

## 阶段 → 资产 Skill

| 七阶段 | 原过程资产阶段 | 资产 Skill |
|---|---|---|
| plan | 01 项目前期 + 02 软件策划 | `p1-software-naming-review`、`p1-software-naming-rules`、`p2-config-management-plan-guide`、`p2-kickoff-meeting-deck`、`p2-management-standards-guide`、`planning-report-template` |
| requirements | 03 需求分析 | `p3-requirements-analysis-report`、`p3-requirements-review-sheet`、`p3-requirements-traceability-matrix` |
| design | 04 设计 | `p4-design-report`、`p4-design-review-sheet`、`p4-theoretical-model-report` |
| implementation | 05 编码实现 | `p5-dev-notes`、`p5-unit-test-execution-record`、`p5-user-manual` |
| test | 06 软件测试 | `p6-test-plan`、`p6-test-report`、`p6-static-defect-explanation`、`p6-testcase-review-sheet`、`p6-unittest-execution-guide` |
| vv | 07 验证与确认（含数据管理） | `p7-vv-outline`、`p7-vv-report`、`p7-vv-review-sheet`、`p7-engineering-validation-record`、`p7-data-*` 六个数据管理 Skill |
| release | 08 发布 + 09 脚本发布 | `p8-release-*`、`p9-script-description` |

数据管理 Skill（属性清单/描述文件/错误更正/入库升版/使用申请/维护）在映射上归 `vv`，但可在任意阶段按需使用；见 [STAGE-MAPPING.md](STAGE-MAPPING.md)。

## 安装

与 `nuclear-setup` 相同的宿主布局，但**独立安装、不覆盖** `nuclear-*` Skill：

```bash
# 预览（默认 dry-run）
python3 process-assets/scripts/install.py dsh --scope project --project <项目> --json

# 确认后写入
python3 process-assets/scripts/install.py dsh --scope project --project <项目> --yes --json
```

支持宿主：`claude`、`codex`、`opencode`、`reasonix`、`generic`、`dsh`、`all`。安装器只复制 `process-assets/skills/` 下的 40 个子目录，排除 `__pycache__` 与 `*.pyc`，写入前对已存在目标做冲突检查，`--force` 才备份覆盖。

## 命名说明

源导出中有 2 个 Skill 名含大写（`p8-release-baseline-A`、`p8-release-baseline-B`），按 Agent Skills 规则规范为小写 `p8-release-baseline-a` / `-b`，原名记录在 frontmatter 的 `metadata.original-name`。

## 重新生成

```bash
python3 tools/split_process_assets.py           # 从 ~/Desktop/资产库.md 重建
python3 tools/split_process_assets.py --check   # 校验已生成文件与源一致
```
