# 数值方法：核工程领域参考

> 参考性材料（公开教材/综述）；不参与门禁判定。

## 中子输运与扩散

- **扩散/节点法**：适合堆芯稳态与瞬态分析；写明能群、节点展开阶数、界面流连续条件、非线性迭代收敛判据。
- **SN（离散纵标）**：写明角度求积阶数、散射各向异性、步进格式与射线效应处理。
- **PN（球谐）**：写明展开阶数与边界条件近似。
- **MOC（特征线法）**：写明角度/空间网格、线段积分、共振自屏蔽与并行追踪策略。
- **Monte Carlo**：写明粒子数、随机数种子、方差控制、统计误差报告方式与临界源迭代收敛判据。

## 燃耗

- 常用方法包括显式/隐式 Euler、预测-校正、CRAM（切比雪夫有理逼近）与矩阵指数法。
- 设计必须写明：燃耗链矩阵构造、核素截断准则、截面随燃耗/温度更新策略、时间步误差控制。
- 报告量包括核素浓度、反应性、功率演化；单位 MWd/tU 或 MWd/tHM 必须固定。

## 热工水力与 CFD

- 单相/两相流、不可压/可压假设、湍流模型、壁面函数与相变模型必须在设计项声明。
- 有限体积/有限元离散、通量格式、压力-速度耦合与时间推进方式影响守恒与稳定性，必须写入设计。
- 多物理耦合（中子学-热工水力-燃耗）需说明耦合变量、映射插值、时间步同步与数据守恒。

## 稳定性与误差

- 时间显格式有 CFL 类限制；隐格式需说明迭代收敛与非线性残差。
- 误差来源：建模误差、离散截断误差、迭代误差、舍入误差、数据/截面不确定度。
- 设计阶段必须给出可验证的误差控制手段：网格/时间步收敛研究、守恒残差、制造解验证计划。

## 来源（教材/综述）

- 中子输运：Duderstadt & Hamilton, *Nuclear Reactor Analysis*；Lewis & Miller, *Computational Methods of Neutron Transport*（[OSTI](https://www.osti.gov/biblio/5538794)）。
- 扩散与节点法：Stacey, *Space-Time Nuclear Reactor Analysis*；Duderstadt & Hamilton 同上。
- CRAM 燃耗：Pusa & Leppänen, *Computing the matrix exponential in burnup calculations*, NSE 164, 281–293 (2009), DOI [10.13182/NSE08-65](https://doi.org/10.13182/NSE08-65)。
- CFD/有限体积：Ferziger & Perić, *Computational Methods for Fluid Dynamics*；LeVeque, *Finite Volume Methods for Hyperbolic Problems*。
- CFL 条件：Courant, Friedrichs & Lewy (1928), DOI [10.1007/BF01448847](https://doi.org/10.1007/BF01448847)。
- 多物理耦合基准：OECD/NEA PWR MSLB Phase III coupled core-plant（[PDF](https://www.oecd-nea.org/upload/docs/application/pdf/2019-12/nsc-doc2003-21.pdf)）；记录网格映射、时间步长、守恒插值、迭代收敛与数据交换接口。
- 具体项目必须结合自身适用标准确认方法可接受性；本文件为公开教材/综述级参考。
