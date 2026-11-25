---
name: p1-software-naming-rules
description: [01项目前期] 软件命名与版本号规则指引（自主软件植物名命名 + 二次开发命名格式）。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "p1-software-naming-rules"
  stage: "plan"
---

# 软件命名规则（p1-software-naming-rules）
## 用途
提供软件所的软件命名与版本号规则，用于为软件命名和版本升级提供依据。

母版：过程资产库V5.0/01_项目前期/01-01.1【指引】软件命名规则.docx

## 规则内容（单张规则表：序号 | 类型 | 规则）
## 自主软件
命名：用"一种植物的英文名"命名（如 SPRUCE、COTTON、FATIG、LINDEN、SOPHORA）。
版本号更新原则（. 分隔 major.minor.build）：
极大改动 → 更新 major（如 1.x → 2.0）
较大更新（新增功能/增量）→ 更新 minor（如 1.0 → 1.1.0）
小修（缺陷修复/优化）→ 更新 build（如 1.0 → 1.0.1）
版本演化示例：1.0 → 1.0.1 → … → 1.1.0 → … → 2.0 → 2.1.0 → … → 3.0 …
## 二次开发软件
命名格式：原软件-原软件版本号-S自身版本号（S = second）。
示例：SCIENCE4.6-S1.0.0
## 生成/使用方式
本 skill 输出命名建议：给定软件性质（自主/二次开发）与变更规模，给出合规的软件英文名和版本号。若用户要求生成 DOCX，可用 python-docx 按"序号|类型|规则"表呈现。
