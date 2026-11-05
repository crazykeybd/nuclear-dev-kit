/**
 * Reads one workspace's nuclear state through the kit's own command line. This module holds no gate rule: it runs
 * `nuclearctl.py status` for every stage and `nuclearctl.py gate <stage>` for the stage the work stands on, parses the
 * JSON those commands print, and adds only what a person needs to see around them: whether the artifact exists, what
 * the approval file says, and which kind of obstacle a stage carries.
 */
import { join } from 'node:path'
import { z } from 'zod'
import { NUCLEAR_STAGES, STAGE_ARTIFACTS, type ApprovalRecord, type GateReport, type NuclearSnapshot, type NuclearStage,
  type ProjectRecord, type SnapshotProblem, type StageReport, type StageState } from './types.ts'

/** Settings the deployment supplies; an empty `kitPath` switches the whole flow off in this agent. */
export interface NuclearSettings { kitPath: string; python: string; timeoutMs: number; maxProjects: number; refreshSeconds: number }
export const NUCLEAR_DEFAULTS: NuclearSettings = { kitPath: '', python: 'python3', timeoutMs: 20_000, maxProjects: 12, refreshSeconds: 30 }

export interface CommandResult { code: number | null; stdout: string; stderr: string }
/** Runs one kit command as the host's user, without a shell; resolves with its exit code and streams. */
export type NuclearRunner = (argv: string[], options: { timeoutMs: number; signal?: AbortSignal }) => Promise<CommandResult>
/** The filesystem facts a scan needs: whether a path exists, and a small file's text when it is readable. */
export interface NuclearIo { exists(path: string): boolean; read(path: string): string | undefined; run: NuclearRunner }

/** The kit's gate command, which is the only judge of a stage. */
export const controlScript = (kitPath: string): string => join(kitPath, 'skills', 'nuclear-dev', 'scripts', 'nuclearctl.py')
/** The kit's library, whose version the panel reports; never imported by this agent, always run as a program. */
export const libraryScript = (kitPath: string): string => join(kitPath, 'skills', 'nuclear-dev', 'scripts', 'nuclearlib.py')
/** Where a workspace keeps the facts the kit writes. */
export const stateDir = (root: string): string => join(root, '.nuclear-dev')
export const approvalPath = (root: string, stage: NuclearStage): string => join(stateDir(root), 'approvals', `${stage}.json`)
export const artifactPath = (root: string, stage: NuclearStage): string => join(stateDir(root), STAGE_ARTIFACTS[stage])

/** Whether the deployment points at a usable kit; nothing is guessed from the working directory. */
export function kitProblem(settings: Pick<NuclearSettings, 'kitPath'>, exists: (path: string) => boolean): SnapshotProblem | undefined {
  if (!settings.kitPath) return { code: 'kit-missing', detail: 'No nuclear-dev-kit is configured for this installation.' }
  for (const path of [controlScript(settings.kitPath), libraryScript(settings.kitPath)]) {
    if (!exists(path)) return { code: 'kit-missing', detail: `The nuclear-dev-kit at ${settings.kitPath} has no ${path}.` }
  }
  return undefined
}

/** Whether the directory holds an initialised kit workspace; a directory without one is an ordinary working copy. */
export const isWorkspace = (root: string, exists: (path: string) => boolean): boolean =>
  exists(join(stateDir(root), 'project.json'))

const StatusSchema = z.object({ ok: z.boolean(), stages: z.record(z.string(), z.object({ passed: z.boolean(),
  errors: z.array(z.string()) })).optional() })
const GateSchema = z.object({ ok: z.boolean(), stage: z.string(), errors: z.array(z.string()) })
const ProjectSchema = z.object({ name: z.string().default(''), project_id: z.string().default(''), kit_version: z.string().default(''),
  safety_classification: z.string().default('pending'), vv_level: z.string().default('pending') })
const ApprovalSchema = z.object({ decision: z.string().default(''), date: z.string().optional(),
  approver: z.object({ name: z.string().default(''), role: z.string().default(''), organization: z.string().default('') }).partial()
    .optional() })

/** Parse one JSON document, or nothing when the text is not JSON (an unreadable kernel, a crash, a wrapper's noise). */
function document(text: string | undefined): unknown {
  if (!text) return undefined
  const start = text.indexOf('{'), end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return undefined
  try { return JSON.parse(text.slice(start, end + 1)) } catch { return undefined }
}

/** The kit's own words for whether a stage is deficient because of a person's signature rather than the work. */
function approvalError(error: string): boolean {
  return error.startsWith('approval.') || error.includes('人工批准') || error.includes('批准失效') || error.includes('批准记录')
}

/** Classify one stage from the facts around it; `present` is read from the filesystem, the rest from the kit's report. */
export function classifyStage(input: { passed: boolean; present: boolean; errors: string[] }): StageState {
  if (input.passed) return 'passed'
  if (!input.present) return 'missing'
  return input.errors.length && input.errors.every(approvalError) ? 'awaiting-approval' : 'blocked'
}

/** One stage's report as the scan assembles it from the kit's status, the artifact's presence and the approval file. */
export function stageReport(stage: NuclearStage, input: { passed: boolean; errors: string[]; present: boolean;
  approval?: ApprovalRecord }): StageReport {
  return { stage, artifact: STAGE_ARTIFACTS[stage], present: input.present,
    passed: input.passed, state: classifyStage(input), errors: input.errors,
    ...input.approval ? { approval: input.approval } : {} }
}

function approvalOf(text: string | undefined): ApprovalRecord | undefined {
  const parsed = ApprovalSchema.safeParse(document(text))
  if (!parsed.success) return undefined
  const { decision, date, approver } = parsed.data
  const name = approver?.name ?? ''
  return { approver: name, decision,
    ...approver?.role ? { role: approver.role } : {}, ...approver?.organization ? { organization: approver.organization } : {},
    ...date ? { date } : {} }
}

function projectOf(text: string | undefined): ProjectRecord | undefined {
  const parsed = ProjectSchema.safeParse(document(text))
  if (!parsed.success) return undefined
  const { name, project_id, kit_version, safety_classification, vv_level } = parsed.data
  return { name, id: project_id, kitVersion: kit_version, safetyClassification: safety_classification, vvLevel: vv_level }
}

/** The argv of one kit command; `--root` precedes the command, as the kit's own help requires. */
export const statusArgv = (settings: Pick<NuclearSettings, 'python' | 'kitPath'>, root: string): string[] =>
  [settings.python, controlScript(settings.kitPath), '--root', root, 'status', '--json']
export const gateArgv = (settings: Pick<NuclearSettings, 'python' | 'kitPath'>, root: string, stage: NuclearStage): string[] =>
  [settings.python, controlScript(settings.kitPath), '--root', root, 'gate', stage, '--json']

/**
 * Read one workspace. The scan runs the kit's status once and, unless every stage passed, its gate for the first stage
 * that has not, so the panel can say what holds that stage back without a person reading seven artifacts.
 */
export async function scanWorkspace(root: string, settings: NuclearSettings, io: NuclearIo, signal?: AbortSignal): Promise<NuclearSnapshot> {
  const checkedAt = new Date().toISOString()
  const missing = kitProblem(settings, io.exists)
  if (missing) return { root, checkedAt, stages: [], problem: missing }
  const status = await io.run(statusArgv(settings, root), { timeoutMs: settings.timeoutMs, ...signal ? { signal } : {} })
  const parsed = StatusSchema.safeParse(document(status.stdout))
  if (!parsed.success) return { root, checkedAt, stages: [], problem: { code: 'tool-failed',
    detail: `nuclearctl.py status printed no usable JSON (exit code ${status.code}). ${(status.stderr || status.stdout).trim().slice(0, 600)}` } }
  const stages = NUCLEAR_STAGES.map(stage => {
    const reported = parsed.data.stages?.[stage]
    const artifact = artifactPath(root, stage)
    return stageReport(stage, { passed: reported?.passed ?? false, errors: reported?.errors ?? ['The kit reported no status for this stage'],
      present: io.exists(artifact), approval: approvalOf(io.read(approvalPath(root, stage))) })
  })
  const next = stages.find(stage => !stage.passed)?.stage
  if (!next) return { root, checkedAt, stages, project: projectOf(io.read(join(stateDir(root), 'project.json'))) }
  const gate = await io.run(gateArgv(settings, root, next), { timeoutMs: settings.timeoutMs, ...signal ? { signal } : {} })
  const gateParsed = GateSchema.safeParse(document(gate.stdout))
  const report: GateReport = gateParsed.success
    ? { stage: next, ok: gateParsed.data.ok, errors: gateParsed.data.errors }
    : { stage: next, ok: false, errors: [`nuclearctl.py gate ${next} printed no usable JSON (exit code ${gate.code}). ${(gate.stderr || gate.stdout).trim().slice(0, 600)}`] }
  return { root, checkedAt, stages, next, gate: report, project: projectOf(io.read(join(stateDir(root), 'project.json'))) }
}
