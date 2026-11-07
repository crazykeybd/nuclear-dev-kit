/**
 * Who does the work: the chief agent that hands it out, and the seven stage agents it hands it to. The table here holds
 * only what a stage agent is called, which Skill it carries its stage out with, and what that stage's artifact is; the
 * judgement of a stage is still nuclearlib's alone, and a stage agent reads it from the kit's command line.
 */
import { NUCLEAR_STAGES, STAGE_ARTIFACTS, STAGE_SKILLS, type NuclearStage } from './types.ts'

/** Text in both interface languages, as the panel shows an agent's name. */
export interface AgentName { zh: string; en: string }

/** One of the seven agents: it owns one stage, its artifact and the gate that judges it. */
export interface StageAgent {
  /** The stage it owns; also its id, as a Ticket records it. */
  stage: NuclearStage
  /** What the panel calls it. */
  name: AgentName
  /** The kit Skill it carries out its stage with. */
  skill: string
  /** The artifact it writes, relative to `.nuclear-dev`. */
  artifact: string
  /** One line on what its stage has to establish, which the panel shows beside its name. */
  mission: AgentName
}

/** The seven stage agents, in the order the kit's gate enforces them. */
export const STAGE_AGENTS: Readonly<Record<NuclearStage, StageAgent>> = {
  plan: { stage: 'plan', name: { zh: '策划智能体', en: 'plan agent' }, skill: STAGE_SKILLS.plan, artifact: STAGE_ARTIFACTS.plan,
    mission: { zh: '确定安全分级、V&V 等级、适用标准、工具鉴定与人员资格，写下可以审计的策划基线', en: 'Fix the safety classification, the V&V level, the standards, the tool qualification and the staffing, and write an auditable planning baseline' } },
  requirements: { stage: 'requirements', name: { zh: '需求智能体', en: 'requirements agent' }, skill: STAGE_SKILLS.requirements, artifact: STAGE_ARTIFACTS.requirements,
    mission: { zh: '把物理模型、数值精度、适用范围、接口与验收方法写成可验证的 REQ 需求基线', en: 'Write the physical models, the numerical accuracy, the applicability, the interfaces and the acceptance methods as a verifiable REQ baseline' } },
  design: { stage: 'design', name: { zh: '设计智能体', en: 'design agent' }, skill: STAGE_SKILLS.design, artifact: STAGE_ARTIFACTS.design,
    mission: { zh: '把 REQ 分配为 DES 设计项，记录架构、控制方程、离散格式、稳定性、守恒与误差分析', en: 'Allocate the REQ requirements as DES design items, with the architecture, the governing equations, the discretisation, stability, conservation and error analysis' } },
  implementation: { stage: 'implementation', name: { zh: '实现智能体', en: 'implementation agent' }, skill: STAGE_SKILLS.implementation, artifact: STAGE_ARTIFACTS.implementation,
    mission: { zh: '把 DES 落实为真实源码 MOD 模块，保持工作区干净，执行可复现构建并登记构建证据', en: 'Turn each DES item into a real source MOD module, keep the workspace clean, build reproducibly and register the build evidence' } },
  test: { stage: 'test', name: { zh: '测试智能体', en: 'test agent' }, skill: STAGE_SKILLS.test, artifact: STAGE_ARTIFACTS.test,
    mission: { zh: '设计并执行单元、模型与系统测试，覆盖守恒、边界、负向与回归，证明每个 MOD 与 REQ 都被检验', en: 'Design and run unit, model and system tests covering conservation, boundaries, negative cases and regression, and show every MOD and REQ is exercised' } },
  vv: { stage: 'vv', name: { zh: '独立验证智能体', en: 'V&V agent' }, skill: STAGE_SKILLS.vv, artifact: STAGE_ARTIFACTS.vv,
    mission: { zh: '执行代码验证、解的验证与确认，记录参考解、收敛阶、基准来源、误差、适用域、不确定性与独立性', en: 'Carry out code verification, solution verification and validation, with reference solutions, orders of convergence, benchmark sources, errors, domain, uncertainty and independence' } },
  release: { stage: 'release', name: { zh: '发布智能体', en: 'release agent' }, skill: STAGE_SKILLS.release, artifact: STAGE_ARTIFACTS.release,
    mission: { zh: '冻结语义版本与源码 revision，写下发布范围、SBOM、复现与回滚证据，并通过递归门禁', en: 'Freeze the semantic version and the source revision, record the scope, the SBOM and the reproduction and rollback evidence, and pass the recursive gate' } },
}

/** The agent that hands the work out: the main Session, which reads requests and dispatches each Ticket to a stage agent. */
export const CHIEF_AGENT = { id: 'chief', name: { zh: '总控智能体', en: 'chief agent' } } as const

/** The stage agent a Ticket's work is on, or nothing when the Ticket names none. */
export const stageAgent = (stage: NuclearStage | undefined): StageAgent | undefined => stage === undefined ? undefined : STAGE_AGENTS[stage]

/** Whether `value` names one of the seven stages, as a Ticket records it. */
export const isNuclearStage = (value: string): value is NuclearStage => (NUCLEAR_STAGES as readonly string[]).includes(value)

/**
 * The stage agent the work passes to next once `stage` is accepted, or nothing when it is the last one: a Ticket the kit
 * accepts at release has no stage agent left, and its final report goes to the person.
 */
export const nextStageAgent = (stage: NuclearStage): StageAgent | undefined => STAGE_AGENTS[NUCLEAR_STAGES[NUCLEAR_STAGES.indexOf(stage) + 1] as NuclearStage]

/** The stages from `stage` on, in the order the gate enforces them, which a person reading a Ticket sees as what is left. */
export const stagesFrom = (stage: NuclearStage): NuclearStage[] => NUCLEAR_STAGES.slice(NUCLEAR_STAGES.indexOf(stage))
