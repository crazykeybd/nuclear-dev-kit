# 核数据与单位：核工程领域参考

> 参考性材料，不替代核数据库官方发布说明或项目适用标准；不参与门禁判定。

## 核数据库与评价文件

常见评价核数据库：ENDF/B、JEFF、JENDL、CENDL、BROND。项目应记录**库名、版本、评价文件发布日期、加工链（如 NJOY 版本）、能群结构与温度点**，并冻结为配置的一部分。版本以各数据库官网发布页为准，项目不得凭印象填写。

| 库 | 稳定/当前版本（2026-11-25 联网核对） | 官网/发布页 |
|---|---|---|
| ENDF/B | VIII.0 广泛使用；已有官方 VIII.1，需核实工具链支持 | [VIII.0](https://www.nndc.bnl.gov/endf-library/B-VIII.0/summary)、[VIII.1](https://www.nndc.bnl.gov/endf-library/B-VIII.1/summary)、[releases](https://www.nndc.bnl.gov/endf-releases) |
| JEFF | JEFF-3.3（2017）稳定；官方最新 JEFF-4.0（2025-06） | [JEFF-3.3](https://databank.io.oecd-nea.org/data/jeff/33/)、[JEFF-4.0](https://databank.io.oecd-nea.org/data/jeff/40/) |
| JENDL | JENDL-5（2021-12，ENDF-6，扩展至 200 MeV）；使用前核对 errata | [JAEA JENDL-5](https://wwwndc.jaea.go.jp/jendl/j5/j5.html) |
| CENDL | CENDL-3.2（2020-06，272 核素）；未核实到 3.3 官方页 | [CNNC](https://en.cnnc.com.cn/2020-06/17/c_1023199.htm)、[IAEA brief](https://nds.iaea.org/public/download-endf/CENDL-3.2/BriefIntroductionCENDL32-June-10.pdf) |
| BROND | BROND-3.1 常见；最新版通过 IAEA NDS / Russia NDC 核实 | [IAEA reaction data](https://nds.iaea.org/pages/reaction-data) |

| 内容 | 项目应记录 |
|---|---|
| 评价库 | 名称、版本、来源 URL、获取日期、校验和 |
| 加工链 | 加工代码与版本、输入参数、温度、能群、散射矩阵处理 |
| 用途 | 中子学、燃耗、屏蔽、剂量、热工水力物性各用哪一套数据 |
| 外推 | 能区/温度/材料外推限制与开放项 |

## 单位与符号约定（推荐在接口需求中固定）

| 量 | 常用单位 | 符号/备注 |
|---|---|---|
| 有效增殖因子 | 无量纲 | keff |
| 反应性 | pcm、Δk/k | ρ = (keff−1)/keff；1 pcm = 1e−5 Δk/k |
| 微观截面 | barn | 1 barn = 1e−28 m² = 1e−24 cm² |
| 中子通量 | n/cm²/s | 标量通量；能群通量按群定义 |
| 能量 | eV、keV、MeV | 必须标明参考系 |
| 温度 | K | 避免 ℃ 与 K 混用 |
| 燃耗 | MWd/tU（或 MWd/tHM） | 必须标明基准质量（U/HM） |
| 富集度 | wt% U-235 | 标明质量分数或原子分数 |
| 功率密度 | W/m³ | 或 W/cm³，接口必须换算统一 |
| 剂量 | Sv、Sv/h | 与辐射权重、组织权重因子对应 |

## 数据质量管理

- 每条数据引用必须能回到评价库版本与加工命令；不能只写"使用 ENDF 数据"。
- 温度插值、共振自屏蔽、散射各向异性、群常数塌缩方法要写入设计与 V&V 计划。
- 数据版本变化会改变基准结论；发布阶段必须冻结数据版本并重跑关键 V&V 算例。
