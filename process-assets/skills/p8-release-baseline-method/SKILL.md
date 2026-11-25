---
name: p8-release-baseline-method
description: [08软件发布] 软件发布基线建立方法指引（SVN trunk→tag 建立发布基线）。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "p8-release-baseline-method"
  stage: "release"
---

# 软件发布基线建立方法（p8-release-baseline-method）
## 用途
指导软件负责人用 SVN 为项目建立发布基线（里程碑 tag）。4 页指引 PDF。

母版：过程资产库V5.0/08_软件发布/08-01.5【指引】软件发布基线建立方法.pdf

## 核心内容
## 定义
基线 = 版本库中某工作版本的"快照"，作为后续开发的正式标准；变更需项目负责人认可；可理解为项目开发里程碑。
## 基线管理
SVN 配置项分布：trunk（开发主干）、branches（开发分支）、tags（开发里程碑）。
达成阶段性稳定版本时，将 trunk 下必要配置项冻结打包成 tag，后续主干开发基于此 tag 继续。tags 目录只有项目负责人有权限配置。
设置基线方法（8 步）
Repo-browser 打开项目 SVN 配置库
选 trunk 路径（以 LINDEN 项目 LD 为例）
trunk 右键 "show log" 查看历史
在 Log Messages 具体 svn 号上右键 "Create branch/tag from revision"
## 建立基线到 tags 库
版本目录命名规则：项目名称+发布版本号（如 LINDEN 1.4.5 → /tags/LINDEN1.4.5），并填写 Log message
刷新 tags 查看基线；trunk 上 "Revision graph" 图形化查看版本路线图
将 tag 版本号填入《软件发布基线配置表》的 SVN 栏目
## 使用方法
作为发布基线建立的操作指引输出步骤；需要时整理为 DOCX/步骤清单。
