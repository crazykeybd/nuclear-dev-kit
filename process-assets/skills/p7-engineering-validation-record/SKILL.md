---
name: p7-engineering-validation-record
description: [07验证与确认] 工程验证（EV）用例执行记录表。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "p7-engineering-validation-record"
  stage: "vv"
---

# 工程验证记录表（p7-engineering-validation-record）
## 用途
生成工程验证（Engineering Validation）用例执行记录表。

母版：过程资产库V5.0/07_软件验证与确认/07-04【模板】工程验证记录表.docx

## 表格字段
抬头：软件名称（XXX）、软件版本（XXX）、执行人（签字）、日期
明细：用例编号 | 用例名称 | 用例描述 | 结论
示例行：EV-01 | XX工程验证测试（说明测试关注的内容） | 说明对工程验证的简要描述 | 通过/不通过
## 填写要点
用例编号格式 EV-XXXX（EV = Engineering Validation，XXXX 为数字编号，使用时删除注释）。
结论取值"通过/不通过"；示例行（EV-01、EV-123）保留供仿写。
## 生成方法
复制母版 DOCX 后用 python-docx 填充行；无母版时按上述字段新建表格。
