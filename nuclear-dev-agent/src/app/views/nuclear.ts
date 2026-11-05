/** Nuclear views: the kit's state, one board per Ticket workspace, and the stage section of a Ticket page. */
import type { NuclearKit, NuclearProject } from '../nuclear.ts'
import { attentionOf, complete, passedCount, type NuclearSettings, type NuclearSnapshot, type SnapshotProblem } from '../../nuclear/index.ts'

export interface NuclearViewHeader {
  /** Absolute path of the kit this installation runs, or empty when the flow is switched off. */
  kitPath: string
  python: string
  refreshSeconds: number
  /** Whether both of the kit's scripts are where the deployment says. */
  ready: boolean
  problem?: SnapshotProblem
  pythonVersion?: string
}
/**
 * One workspace as the panel shows it: the project the kit recorded, its seven stages, and the gate of the stage the
 * work stands on. A scan problem is shown in place of the board rather than as an empty one.
 */
export function nuclearProjectView(project: NuclearProject) {
  const { snapshot } = project
  return { root: project.root, tickets: project.tickets, checkedAt: snapshot.checkedAt,
    ...snapshot.project ? { project: snapshot.project } : {},
    stages: snapshot.stages, ...snapshot.next ? { next: snapshot.next } : {}, ...snapshot.gate ? { gate: snapshot.gate } : {},
    ...snapshot.problem ? { problem: snapshot.problem } : {},
    passed: passedCount(snapshot), complete: complete(snapshot),
    attention: attentionOf(snapshot)?.stage }
}
export type NuclearProjectView = ReturnType<typeof nuclearProjectView>
/** Counts over the workspaces, for the panel's status line and the overview. */
export function nuclearCounts(projects: readonly NuclearProject[]) {
  const stages = projects.flatMap(project => project.snapshot.stages)
  return { projects: projects.length, passed: stages.filter(stage => stage.passed).length,
    awaiting: stages.filter(stage => stage.state === 'awaiting-approval').length,
    blocked: stages.filter(stage => stage.state === 'blocked').length,
    missing: stages.filter(stage => stage.state === 'missing').length,
    complete: projects.filter(project => complete(project.snapshot)).length }
}
/**
 * What the overview lists about the flow: the stage each workspace stands on when that stage needs a person or the work,
 * with the kit's first errors; an empty list once every stage that was started passed.
 */
export function overviewNuclear(projects: readonly NuclearProject[], limit = 5) {
  const attention = projects.flatMap(project => {
    const stage = attentionOf(project.snapshot)
    return stage ? [{ root: project.root, tickets: project.tickets, stage: stage.stage, state: stage.state,
      errors: stage.errors.slice(0, 3) }] : []
  }).slice(0, limit)
  return { counts: nuclearCounts(projects), attention }
}
export type OverviewNuclear = ReturnType<typeof overviewNuclear>
/** What a person must look at across the workspaces: stages that wait for a signature, stages the work must fix, problems. */
export function nuclearView(input: { settings: NuclearSettings; kit: NuclearKit; interpreter?: SnapshotProblem;
  projects: readonly NuclearProject[]; omitted?: number }) {
  const { settings, kit, interpreter, projects, omitted = 0 } = input
  return {
    configured: !!settings.kitPath,
    header: { kitPath: settings.kitPath, python: settings.python, refreshSeconds: settings.refreshSeconds, ready: kit.ready,
      ...kit.problem ? { problem: kit.problem } : {}, ...kit.pythonVersion ? { pythonVersion: kit.pythonVersion } : {},
      ...interpreter ? { interpreterProblem: interpreter } : {} } satisfies NuclearViewHeader & { interpreterProblem?: SnapshotProblem },
    counts: nuclearCounts(projects),
    // The cap on scanned directories is reported, not hidden: a short board must not look complete.
    ...omitted ? { omitted } : {},
    projects: projects.map(nuclearProjectView),
  }
}
export type NuclearView = ReturnType<typeof nuclearView>
/** The stage rows a Ticket page shows: the same reports the board shows, without the workspace's other Tickets. */
export function ticketNuclearView(snapshot: NuclearSnapshot) {
  return { checkedAt: snapshot.checkedAt, stages: snapshot.stages, ...snapshot.project ? { project: snapshot.project } : {},
    ...snapshot.next ? { next: snapshot.next } : {}, ...snapshot.gate ? { gate: snapshot.gate } : {},
    ...snapshot.problem ? { problem: snapshot.problem } : {}, passed: passedCount(snapshot), complete: complete(snapshot),
    attention: attentionOf(snapshot)?.stage }
}
export type TicketNuclearView = ReturnType<typeof ticketNuclearView>
