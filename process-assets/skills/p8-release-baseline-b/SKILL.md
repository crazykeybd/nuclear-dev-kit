---
name: p8-release-baseline-b
description: [08软件发布] 软件发布基线配置表-安全B类（XLSX，技术文件基线，仅需求/编码/测试）。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "p8-release-baseline-B"
  stage: "release"
---

# 软件发布基线配置表-安全B类（p8-release-baseline-B）
## 用途
安全 B 类软件发布基线配置表（内容比 A 类简化）。

母版：过程资产库V5.0/08_软件发布/08-01.2【模板】软件发布基线配置表-安全B类.xlsx

## 结构
单工作表 Sheet1：头部信息区 + 「技术文件基线组成列表」明细表 + 签字区。

## 字段/列
头部：软件名称、软件代号、基线版本、SVN号、时间、系统管理员[签字]
明细表（表头「技术文件基线组成列表」）：配置管理项名称、编码、版本（阶段：软件需求分析 / 软件编码 / 软件测试）
底部：质量工程师、软件负责人
## 填写要点
仅列出涉及的成果物技术文件（三者：需求分析、编码、测试）。
示例：FDMAP（核燃料数据管理和分析平台）v2.1.0；SVN 号留空、版本均为 A。
## 生成方法
用 python-exec（openpyxl）生成 Sheet1。
