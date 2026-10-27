---
name: nuclear-setup
description: 初始化核能软件开发工作区并安装七阶段 Skill 包。用于新项目建立 .nuclear-dev 门禁目录，或在 Claude Code、Codex、opencode、Reasonix 和通用代理中部署受控研发流程。
license: MIT
metadata:
  version: "0.1.0"
---

# 核能软件开发环境部署

## 工程边界

> 不替代签署、监管判断或真实测试；不生成批准；不伪造结果；门禁失败即停止。
> 门禁通过不等同监管批准或真实工程合规。

## 目标

建立项目中的 `.nuclear-dev` 门禁工作区，或把 `skills/` 下十个 Skill 安装到指定宿主。此 Skill 不进行工程批准，也不修改项目源码。

日常安装/升级建议先使用 `nuclear-install`：它自动检测宿主、预览、写入、初始化并验证，底层仍调用本目录的 `scripts/install.py`。

## 初始化项目

先从当前任务确定项目根目录和目标语言运行时，然后执行：

```bash
python3 <SKILL_DIR>/../nuclear-dev/scripts/nuclearctl.py --root <项目> init \
  --name <项目名称> --id <小写项目标识> --json
```

初始化只创建结构、项目元数据和空索引；不会创建阶段产物或人工批准。已初始化时不要删除或重建，改用 `status` 和 `validate` 检查。

## 安装 Skill

安装器位于本目录的 `scripts/install.py`，源目录由脚本自动解析为整个包的 `skills/`：

```bash
python3 <SKILL_DIR>/scripts/install.py <claude|codex|opencode|reasonix|generic|all> \
  --scope <project|global> [--project <项目>] --json
```

默认是 dry-run。检查 JSON 中的 `targets`、`status` 和冲突后，只有用户明确同意写入时加 `--yes`。目标存在时默认拒绝；`--force` 才会备份并替换。`all` 按绝对目标路径去重，避免重复复制。

## 验证

安装后检查：

1. 每个目标目录都有 `SKILL.md`，且十个 Skill 均可读。
2. `nuclearctl.py --root <项目> status --json` 能返回七阶段状态。
3. 工具无法执行时如实报告，不把静态复制说成门禁通过。
4. 新会话中运行一次 `nuclear-plan` 的只读检查；只有状态与门禁结果真实通过才继续下一阶段。

人工批准文件永远不由本 Skill 或安装器生成。需要批准时停止并把产物交给有权限人员单独审查。
