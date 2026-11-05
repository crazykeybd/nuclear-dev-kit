/**
 * The nuclear development flow as this agent shows it: the kit's seven stages, what each one's artifact is, and the
 * facts a workspace scan produces. The judgement itself is never made here: a stage's `passed` and its `errors` are
 * nuclearlib's own words, so the panel and the agents read one set of rules.
 */

/** The seven stages in the order the kit's gate enforces them. */
export const NUCLEAR_STAGES = ['plan', 'requirements', 'design', 'implementation', 'test', 'vv', 'release'] as const
export type NuclearStage = typeof NUCLEAR_STAGES[number]

/** Each stage's artifact, relative to `.nuclear-dev`, as the kit names it. */
export const STAGE_ARTIFACTS: Readonly<Record<NuclearStage, string>> = {
  plan: 'stages/plan/plan.json',
  requirements: 'stages/requirements/requirements.json',
  design: 'stages/design/design.json',
  implementation: 'stages/implementation/implementation.json',
  test: 'stages/test/test-report.json',
  vv: 'stages/vv/vv-report.json',
  release: 'stages/release/release.json',
}

/** The Skill that carries out each stage. */
export const STAGE_SKILLS: Readonly<Record<NuclearStage, string>> = {
  plan: 'nuclear-plan',
  requirements: 'nuclear-requirements',
  design: 'nuclear-design',
  implementation: 'nuclear-implementation',
  test: 'nuclear-test',
  vv: 'nuclear-vv',
  release: 'nuclear-release',
}

/**
 * Why a stage is not done: `passed` when the kit's gate accepts it, `missing` when its artifact was never written,
 * `awaiting-approval` when only a person's signed approval is absent or no longer valid, and `blocked` otherwise.
 */
export type StageState = 'passed' | 'missing' | 'awaiting-approval' | 'blocked'

/** What one stage's approval file says; a signature this agent cannot verify is never asserted as valid. */
export interface ApprovalRecord { approver: string; role?: string; organization?: string; decision: string; date?: string }

export interface StageReport {
  stage: NuclearStage
  /** The artifact path relative to `.nuclear-dev`. */
  artifact: string
  /** Whether that artifact exists; written by the agent, read here to tell "not started" from "not accepted". */
  present: boolean
  /** The kit's verdict for this stage alone, without its dependencies. */
  passed: boolean
  state: StageState
  /** The kit's errors, verbatim: this agent words none of them itself. */
  errors: string[]
  approval?: ApprovalRecord
}

/** One stage's gate with its dependencies, run only for the stage the work is on. */
export interface GateReport { stage: NuclearStage; ok: boolean; errors: string[] }

/** The kit's project metadata for the workspace (`.nuclear-dev/project.json`). */
export interface ProjectRecord { name: string; id: string; kitVersion: string; safetyClassification: string; vvLevel: string }

/** Why a workspace could not be read at all. */
export interface SnapshotProblem { code: 'kit-missing' | 'uninitialised' | 'tool-failed' | 'unreadable'; detail: string }

export interface NuclearSnapshot {
  /** The workspace directory the kit is asked about. */
  root: string
  checkedAt: string
  project?: ProjectRecord
  stages: StageReport[]
  /** The first stage the gate does not accept, which is where the work stands. */
  next?: NuclearStage
  /** That stage's gate, with its dependencies' errors, or absent when every stage passed. */
  gate?: GateReport
  problem?: SnapshotProblem
}

/** The stage a person or the agent has to deal with next, or none once everything the kit checks passed. */
export function attentionOf(snapshot: NuclearSnapshot): StageReport | undefined {
  return snapshot.stages.find(stage => stage.state === 'awaiting-approval') ?? snapshot.stages.find(stage => stage.state === 'blocked')
}
/** How many stages the kit accepted. */
export function passedCount(snapshot: NuclearSnapshot): number {
  return snapshot.stages.filter(stage => stage.passed).length
}
/** Whether the flow is done: every stage passed. */
export function complete(snapshot: NuclearSnapshot): boolean {
  return snapshot.stages.every(stage => stage.passed)
}
/** A workspace's stage report by name, or nothing when the snapshot has none for it. */
export function reportIn(snapshot: NuclearSnapshot, stage: string): StageReport | undefined {
  return snapshot.stages.find(item => item.stage === stage)
}
