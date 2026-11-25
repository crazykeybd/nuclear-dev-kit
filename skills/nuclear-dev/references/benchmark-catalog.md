# 基准题目录：核工程领域参考

> 参考性材料。**基准题必须可公开核查、版本与算例可追溯**；引用内容与测量不确定度必须记入 V&V 产物。本文件不参与门禁判定。
>
> 联网核对：2026-11-25。多数国际基准题公开发布目录/论文，但完整数据集通常需向 NEA Data Bank 申请并签署使用条件；"网页可检索"不等于"可再分发"。

## 原则

- 引用时写清：机构/项目名、版本或发布年份、具体算例编号、数据来源 URL、获取日期、本地副本校验和。
- 只用项目适用域内的基准；外推必须写进限制与残余风险。
- 不使用"内部数据""未公开报告"作为独立确认依据；来源不明的内容进入 `open_items`。
- 遵守数据访问授权与再分发限制；不得把受控基准数据随公共包外发。

## 可公开引用的基准族（按用途）

| 用途 | 基准族 | 来源 |
|---|---|---|
| 临界安全/中子输运 | OECD/NEA ICSBEP，Handbook 提供经评估的临界实验规格 | [NEA Data Bank ICSBEP](https://databank.io.oecd-nea.org/benchmarks/icsbep/)；2021 Handbook DOI [10.1787/110ba6fc-en](https://doi.org/10.1787/110ba6fc-en) |
| 燃耗信用/临界 | OECD/NEA Burnup Credit Criticality Benchmark（Phase I/II/VIII 等） | [NEA BUC report](https://oecd-nea.org/upload/docs/application/pdf/2023-08/nea_nsc_r_2022_3_corr_2023-08-31_09-33-37_204.pdf)、[OECD publication](https://www.oecd.org/en/publications/burn-up-credit-criticality-benchmark_9789264103498-en.html)、[NEA BUC](https://www.oecdnea.org/science/wpncs/buc/) |
| 热工水力/LOCA | LOFT（失流试验）、ROSA/KAERI（CSNI 国际基准/盲算） | [NEA LOFT](https://www.oecd-nea.org/jcms/pl_25963/loss-of-fluid-test-loft-project)、[CSNI2009 ROSA](http://harbor.oecd-nea.org/tools/abstract/detail/csni2009) |
| 主蒸汽管破裂/耦合 | PWR MSLB（堆芯-厂房耦合瞬态） | [PWR MSLB Vol. IV Phase III](https://www.oecd-nea.org/upload/docs/application/pdf/2019-12/nsc-doc2003-21.pdf) |
| 严重事故/系统瞬态 | TMI-1 相关数据可作为来源，但需按 NEA/CSNI 目录逐项确认单一基准报告与访问条件 | [NEA 3D system-scale TH code status](https://oecd-nea.org/upload/docs/application/pdf/2024-05/nea_csni_r_2020_6.pdf) |
| 屏蔽/剂量 | SINBAD（反应堆/加速器/聚变屏蔽积分基准，>100 个算例）、IAEA 屏蔽报告 | [NEA SINBAD](https://databank.io.oecd-nea.org/benchmarks/sinbad/)；论文 DOI [10.1016/j.anucene.2021.108254](https://doi.org/10.1016/j.anucene.2021.108254)；[IAEA INDC report](https://nds.iaea.org/publications/indc/indc-nds-0066.pdf) |
| IAEA 临界安全 | IAEA 指南要求对计算方法与核数据 V&V；数值验证常采用 ICSBEP 或国家监管认可基准集。未核实到与 ICSBEP 等价、完全开放的"IAEA 单一基准库" | [IAEA SSG-27 V&V 章节](https://nucleus.iaea.org/sites/nss-oui/Published%20Chunks/m_50d5ac40-0b83-46c9-9192-223620d551fe/c_ddf0c87c-a229-4b89-a6df-1140f19e8b78__7_0.Html) |
| 制造解方法（MMS） | 代码验证：构造解析解、检查离散收敛阶；不等同物理确认 | Roache, *J. Fluids Eng.* 124(1), 4–10, DOI [10.1115/1.1436090](https://doi.org/10.1115/1.1436090)；Oberkampf & Trucano, *Prog. Aerosp. Sci.* 38, 209–272, DOI [10.1016/S0376-0421(02)00005-2](https://doi.org/10.1016/S0376-0421(02)00005-2) |

> 上表链接指向机构页面或入口；具体算例的版本、编号和获取条件需在对应数据库中核对。链接失效时以本地副本与校验和为准。

## 与 V&V 的接口

- `code_verification.reference_solution`：解析解、制造解或独立实现，必须引用来源。
- `solution_verification.convergence_study`/`observed_order`：网格/时间步序列、拟合方法与阶数。
- `validation.benchmark_source`/`applicability_domain`/`error_metrics`/`trends`：基准来源、适用域、误差指标与趋势必须非空且可核查。

## 核数据版本

基准结论与核数据版本绑定。版本以各库官网为准，不得凭印象填写；记录库名、版本、处理链与校验和。

| 库 | 当前稳定/官方版本（2026 核对） | 来源 |
|---|---|---|
| ENDF/B | VIII.0 广泛使用；已有官方 VIII.1 发布页，需核实工具链支持 | [VIII.0](https://www.nndc.bnl.gov/endf-library/B-VIII.0/summary)、[VIII.1](https://www.nndc.bnl.gov/endf-library/B-VIII.1/summary)、[releases](https://www.nndc.bnl.gov/endf-releases) |
| JEFF | JEFF-3.3（2017-11-20）稳定；官方最新 JEFF-4.0（2025-06） | [JEFF-3.3](https://databank.io.oecd-nea.org/data/jeff/33/)、[JEFF-4.0](https://databank.io.oecd-nea.org/data/jeff/40/) |
| JENDL | JENDL-5（2021-12，ENDF-6，扩展至 200 MeV），使用前核对 errata | [JAEA JENDL-5](https://wwwndc.jaea.go.jp/jendl/j5/j5.html) |
| CENDL | CENDL-3.2（2020-06-12，272 核素）；未核实到 3.3 官方页 | [CNNC release](https://en.cnnc.com.cn/2020-06/17/c_1023199.htm)、[IAEA brief](https://nds.iaea.org/public/download-endf/CENDL-3.2/BriefIntroductionCENDL32-June-10.pdf) |
| BROND | BROND-3.1 常见；最新版通过 IAEA NDS / Russia Nuclear Data Center 核实，暂标"待项目确认" | [IAEA reaction data](https://nds.iaea.org/pages/reaction-data) |
