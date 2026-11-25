---
name: process-asset-router
description: [路由] 根据用户提到的软件生命周期阶段/文档类型，自动选择并调用过程资产库对应的可复用 skill（入口路由）。
license: MIT
metadata:
  version: "5.0.0"
  original-name: "process-asset-router"
  stage: "router"
---

# 过程资产库 Skill 路由器（process-asset-router）
## 用途
这是过程资产库 Skill 套件的统一入口。当用户提到以下任一类话题时，先由本 skill 判定目标阶段/文档，再转调对应的 pX-* skill 生成产物。

## 判定流程（先分类，再转调）
识别阶段：从用户表述提取软件生命周期阶段（项目前期 / 策划 / 需求分析 / 设计 / 编码 / 测试 / 验证与确认 / 发布 / 脚本发布）或文档类型。
匹配 skill：按下表定位对应 skill（可多选，如"发布评审"命中评审PPT+流程指引）。
转调：用 run_skill({ name: "<skill>", arguments: "<用户原始需求/素材>" }) 执行；同一需求涉及多阶段时按 1 策划→2 需求→3 设计→4 编码→5 测试→6 V&V→7 发布 的顺序逐个调用。
回退：命中"参考资料类"（旧格式/案例/教程）或无法匹配时，告知用户该资料仅登记于 过程资产库V5.0，可由 skill navigate-index（分类索引 README）或人工查阅，不强行转调。
## 路由表（阶段关键词 → skill）
## 01 项目前期
关键词	Skill
软件命名、命名评审、软件名审核	p1-software-naming-review
命名规则、版本号规则、命名规范	p1-software-naming-rules
## 02 软件策划
关键词	Skill
策划报告、软件策划书、项目策划	planning-report-template（以及 p2-management-standards-guide 供 2.1 节约引用）
遵循的管理标准、管理程序清单、标准程序	p2-management-standards-guide
配置管理计划、项目管理计划	p2-config-management-plan-guide
启动会议、kickoff、宣讲材料	p2-kickoff-meeting-deck
## 03 软件需求分析
关键词	Skill
需求分析报告、需求规格	p3-requirements-analysis-report
需求跟踪矩阵、追溯矩阵	p3-requirements-traceability-matrix
需求评审、需求过程评审单	p3-requirements-review-sheet
## 04 软件设计
关键词	Skill
理论模型、物理模型报告、数学模型	p4-theoretical-model-report
设计报告、概要/详细设计、模块设计	p4-design-report
设计评审、设计过程评审单	p4-design-review-sheet
## 05 软件编码实现
关键词	Skill
用户手册、操作手册、使用说明	p5-user-manual
开发笔记、模块开发笔记	p5-dev-notes
单元测试执行记录、测试记录表	p5-unit-test-execution-record
## 06 软件测试
关键词	Skill
测试计划	p6-test-plan
测试报告	p6-test-report
静态测试缺陷、误判解释	p6-static-defect-explanation
测试用例评审、用例评审单	p6-testcase-review-sheet
单元测试执行指引、覆盖率考核	p6-unittest-execution-guide
## 07 软件验证与确认
关键词	Skill
V&V 大纲、验证与确认大纲	p7-vv-outline
V&V 报告、验证与确认报告	p7-vv-report
验证过程评审、V&V评审单	p7-vv-review-sheet
工程验证、EV记录表	p7-engineering-validation-record
数据错误更正	p7-data-error-correction
数据描述文件	p7-data-description-file
数据入库、数据升版审批	p7-data-in-out-approval
数据属性清单	p7-data-attribute-list
数据使用申请	p7-data-use-application
数据维护	p7-data-maintenance
（数据管理通用）	先判具体动作，再选上述 data-*
## 08 软件发布
关键词	Skill
发布基线配置表-安全A类	p8-release-baseline-A
发布基线配置表-安全B类	p8-release-baseline-B
发布基线配置表-非安管理类	p8-release-baseline-nonsafety
发布评审-安全A类 PPT	p8-release-review-deck-A
发布评审-非安管理类 PPT	p8-release-review-deck-nonsafety
基线建立方法、SVN基线	p8-release-baseline-method
正式版本发布流程、发布指引、发布检查单	p8-release-process-guide
发布评审会组织、会议指南	p8-release-review-meeting-guide
## 09 脚本发布
关键词	Skill
脚本说明书、安全脚本	p9-script-description
## 分类判定辅助（文件种类/类型）
用户给出软件分类时辅助定位：安全分析 A 类 → 全套 PIPT 过程（策划/需求/设计/理论模型/测试/V&V/发布基线 A 类/发布评审 A 类）；安全 B 类 → 发布基线 B 类；非安管理/设计类 → 发布基线非安类 + 发布评审非安类。
用户给出文档类型但未提阶段时，用文档名反向映射到阶段（如"测试计划"→06；"用户手册"→05）。
## 参考资料回退词表（不转调，只登记提示）
.msg 命名评审邮件、.xls 配置管理计划旧版、.doc 会议纪要/需求申请单/发布评审单/知识产权审查单、弃用/试行版本、测试工具教程（C++test/GTEST/JTest/JUnit/PyTest）、发布评审案例 PPT、测试版本发布规则 PDF、10-示例 全部 PDF、宣贯材料 —— 提示用户从 D:\P0\work\过程资产库V5.0\ 对应路径人工查阅，或由索引 README 定位。
## 注意事项
路由 skill 本身不生成文档，只负责分发；若用户未指定具体文档，询问所需阶段/文档类型后再路由。
多文档需求（如"一个软件从策划到发布的全套资料"）按阶段顺序逐个转调并汇总各 skill 的产出清单。
调用具体 skill 时，把用户原始需求与已确认的项目信息（软件名、版本、人员、进度等）作为 arguments 透传。

## 目录
