---
name: p8-release-baseline-nonsafety
description: [08软件发布] 软件发布基线配置表-非安管理类（XLSX，含策划/需求/设计/编码/测试）。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "p8-release-baseline-nonsafety"
  stage: "release"
---

# 软件发布基线配置表-非安管理类（p8-release-baseline-nonsafety）
## 用途
非安（非安全管理类）软件发布的基线配置表。

母版：过程资产库V5.0/08_软件发布/08-01.4【模板】软件发布基线配置表-非安管理类.xlsx

## 结构
单工作表 Sheet1：头部信息区 + 「基线组成列表」明细表 + 签字区。

## 字段/列
头部：软件名称、软件代号、基线版本、SVN号、时间、系统管理员[签字]
明细表：配置管理项名称、编码、版本（阶段覆盖：软件策划 / 软件需求分析 / 软件设计 / 软件编码 / 软件测试；比 B 类多策划与设计，无 V&V）
底部：质量工程师、软件负责人
## 填写要点
非安管理类需按策划→需求→设计→编码→测试完整列出成果物。
示例 FDMAP v2.1.0；编码格式 CNPRI-GN-F11-21SDC003-00X，版本 A。
## 生成方法
用 python-exec（openpyxl）生成 Sheet1。
