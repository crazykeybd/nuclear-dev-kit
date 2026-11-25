# 适用标准谱系：核工程领域参考

> 参考性材料，**不替代标准原文、项目所在地法规或持证人员判断**。是否强制采用某标准，必须由项目按合同与监管框架确认。本文件不参与门禁判定。
>
> 联网核对：2026-11-25。标准的现行版、强制性与许可证适用性必须由项目所在地的持证核安全/QA 人员确认。

## 来源层级

| 层级 | 含义 | 举例 |
|---|---|---|
| 法规 | 项目所在地监管机构依法要求，具强制力 | 国家核安全法规、美国 10 CFR 50 Appendix B、DOE O 414.1D（DOE 内部） |
| 标准 | 标准组织发布；只有被法规、合同、许可证或设计基准引用后才成为强制 | IEC、IEEE、ASME、ISO |
| 指南/报告 | 监管机构或研究机构的技术指导，不当然具有法律效力 | IAEA SSG/NS-G 系列、IAEA/NEA 技术报告、NASA-STD-7009B |

**易混淆点**：IEEE Std 380 是 1E 级电缆与现场接头的鉴定标准，不是软件标准；IAEA SSG-34 是核电厂电力系统设计指南，不是软件 V&V 标准；DOE-STD-1027 是危险分类与事故分析方法，不是软件 QA 标准。软件 QA 在 DOE 体系下对应 DOE O 414.1D + DOE Guide 414.1-4。

## 安全级仪控与软件

| 标准 | 主题（版本与性质） | 来源 |
|---|---|---|
| IEC 60880 | 执行 Category A 功能计算机化 I&C 系统的软件方面；IEC 60880:2006 (Ed. 2)。标准，非法规 | [IEC Webstore](https://webstore.iec.ch/en/publication/3795) |
| IEC 62138 | 执行 Category B/C 功能计算机化 I&C 系统的软件方面；IEC 62138:2018。与 60880 互补 | [IEC Webstore](https://webstore.iec.ch/en/publication/30172) |
| IEEE Std 7-4.3.2 | 可编程数字设备准则，补充 IEEE Std 603；IEEE Std 7-4.3.2-2016（Active；2025 有修订草案活动） | [IEEE SA](https://standards-dev21.ieee.org/ieee/7-4.3.2/5778/) |
| IEC 61508 | E/E/PES 功能安全基础标准，-3:2010 为软件要求；非核专用，可作方法学参考 | [61508-1](https://webstore.iec.ch/en/publication/5515)、[61508-3](https://webstore.iec.ch/en/publication/5517) |
| IEC 61511 | 流程工业安全仪表系统（SIS）；非核 I&C 专用，可作 SIS 生命周期参考 | [61511-1](https://webstore.iec.ch/en/publication/24241) |
| IAEA NS-G-1.3 → SSG-39 | NS-G-1.3 (2002) 已被 SSG-39 *Design of I&C Systems for NPP* (2016) 取代；均为 IAEA 安全指南 | [NS-G-1.3](https://www.iaea.org/publications/6206/instrumentation-and-control-systems-important-to-safety-in-nuclear-power-plants)、[SSG-39](http://www-pub.iaea.org/MTCD/publications/PDF/Pub1694web-90481357.pdf) |
| IAEA SSG-34 | 核电厂电力系统设计（**不是软件标准**）；状态/替代关系按 IAEA 目录核实 | [IAEA superseded standards](https://ns-files.iaea.org/standards/superseded-safety-standards.pdf) |

## 核质保与配置管理

| 标准 | 主题 | 备注 |
|---|---|---|
| ASME NQA-1 | 核设施全生命周期 QA（含软件验证确认与配置管理） | 官网当前展示 NQA-1-2026（稳定维护）；被合同/监管引用后强制。[ASME](https://www.asme.org/codes-standards/find-codes-standards/quality-assurance-requirements-for-nuclear-facility-applications/2024/print-book) |
| 10 CFR 50 Appendix B | 核电厂与燃料后处理设施 QA criteria | US NRC 法规，对范围内许可证持有者强制。[eCFR](https://www.ecfr.gov/current/title-10/chapter-I/part-50/subject-group-ECFR89aa6ca4aada73c/appendix-Appendix%20B%20to%20Part%2050) |
| DOE O 414.1D + DOE Guide 414.1-4 | DOE QA Order 与安全软件指南（对应 10 CFR 830 Subpart A） | DOE 内部强制；414.1E 草案状态需核实。[DOE Guide 414.1-4](https://www.energy.gov/sites/prod/files/hss/Enforcement%20and%20Oversight/Enforcement/docs/guides/DOE_Guide_414_1_4.pdf)、[DOE O 414.1D](https://www.energy.gov/sites/prod/files/em/DOEOrder414.1D.pdf) |

## 软件 V&V 与建模仿真

| 文件 | 主题 | 备注 |
|---|---|---|
| ASME V&V 10 | 计算固体力学 V&V/VVUQ；V&V 10-2019 (R2025) | consensus 标准。[ASME](https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-solid-mechanics/2019/pdf) |
| ASME V&V 20 | CFD 与传热计算 V&V；V&V 20-2009 (R2021)，适合热工水力 CFD 子模型 | [ASME](https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-fluid-dynamics-and-heat-transfer/2009/print-book) |
| NASA-STD-7009B | 建模与仿真 V&V/UQ；2024-03-05 Active | NASA 页面标注 **Not a NASA Mandatory Standard**；核项目仅作方法借鉴。[NASA NTSS](https://standards.nasa.gov/node/263) |

## 使用纪律

- 在 `plan` 阶段的 `standards` 中逐项写 `id/title/revision/applicability/status/source`；把"是否适用"与"状态"分开，不要混为一句"符合标准"。
- 不要把一般行业惯例或已废止指南写成强制标准；引用版本必须可追溯到具体发布年份与来源。
- 对方才提到的"非软件标准"（IEEE 380、SSG-34、DOE-STD-1027）不得填入软件标准清单，除非说明其外围用途。
