/**
 * A deployment's Ticket worktrees: the directory a Ticket's worker starts in, created from the configured repository when it is
 * missing, and removed once the Ticket ended and its branch would add nothing to the base branch.
 * The lifecycle is the one a person asks of `wt switch` and `wt remove`: a branch the repository already has is checked out
 * again rather than refused, and a worktree goes only with its work in the base branch, its branch and its uncommitted paths kept
 * otherwise. A worktree that is kept stays, and the sweep says why, so nothing is discarded silently.
 */
import { mkdir } from 'node:fs/promises'
import { dirname, isAbsolute, resolve } from 'node:path'
import type { SubprocessRuntime } from '@deepseek-ai/dsh-subprocess'
import type { Ticket } from '../core/index.ts'
import { KV } from '../kv.ts'
import type { Settings, WorktreeConfig } from '../policy.ts'
import { runAsWorker } from '../infra/environment.ts'
import { Worktrees, gitRun, renderWorktree, repositoryName, within, type WorktreeNames } from '../infra/worktrees.ts'
import type { Store } from '../app/store.ts'
import type { Variable } from '../app/execution-environment.ts'
import { executionRoot } from '../app/execution-environment.ts'

/** How long a worktree hook may run: a create hook often installs dependencies, and a remove hook saves what it must. */
const CREATE_HOOK_MS = 10 * 60_000, REMOVE_HOOK_MS = 5 * 60_000
/** How long one git command of the lifecycle may take. */
const GIT_MS = 60_000
/** One worktree as the panel and the tool show it: where it stands, and the Ticket that works in it, when one does. */
export interface WorktreeRow {
  path: string
  branch?: string
  head?: string
  detached: boolean
  prunable?: string
  /** Uncommitted paths, which keep a sweep from removing the worktree. */
  dirty: number
  /** Commits the branch has beyond the base, and the base has beyond it. */
  ahead: number
  behind: number
  /** Whether the branch would add nothing to the base, which is what lets a sweep remove this worktree. */
  merged: boolean
  /** The Ticket of this directory, `open` while its worker may still write there. */
  ticket?: { id: string; title: string; open: boolean }
}
/** What one cleanup sweep did: the worktrees it removed, the ones it kept and why, and how many stale records it dropped. */
export interface WorktreeSweep {
  at: string
  removed: { path: string; branch?: string; ticket?: string }[]
  kept: { path: string; branch?: string; ticket?: string; reason: string }[]
  pruned: number
}
/** What removing one worktree did, and why it may have stayed. */
export interface WorktreeRemoval { path: string; branch?: string; removed: boolean; branchDeleted?: boolean; reason?: string }
/** Host dependencies of `TicketWorktrees`. */
export interface WorktreesHost {
  readonly subprocess: SubprocessRuntime
  readonly store: Pick<Store, 'tickets' | 'settings' | 'get' | 'set'>
  readonly machine: { readonly stateDir: string }
  /** Execution environment variables for a Ticket, which its worktree hooks read as their environment. */
  environment(ticket: Ticket): Variable[]
  readonly lifetime: AbortSignal
}

/**
 * The Ticket worktrees of one deployment, as the Executor creates them and cleans up after them.
 * Every method reads the settings afresh, so a save takes effect on the next Ticket without a restart.
 */
export class TicketWorktrees {
  /** The sweep in flight, so a timer and a person asking at the same moment sweep once. */
  private sweeping?: Promise<WorktreeSweep | undefined>
  constructor(private readonly host: WorktreesHost) {}

  /** The worktree settings of the deployment; `repository` empty means the prepare command creates Ticket directories instead. */
  config(settings: Settings = this.host.store.settings()): WorktreeConfig { return settings.executor.worktrees }
  /** The execution root, below which a Ticket's directory stands unless its path template says otherwise. */
  root(): string { return executionRoot(this.host.store.settings(), this.host.machine.stateDir) }
  /** The repository's worktrees, or undefined when the deployment has no repository to create them from. */
  manager(settings: Settings = this.host.store.settings()): Worktrees | undefined {
    const { repository } = settings.executor.worktrees
    return repository ? new Worktrees(gitRun(this.host.subprocess), repository) : undefined
  }
  /** The names a Ticket's path and branch templates render from. */
  names(ticket: Ticket, settings: Settings = this.host.store.settings()): WorktreeNames {
    return { name: ticket.execution?.name ?? ticket.id, ticket: ticket.id, repo: repositoryName(settings.executor.worktrees.repository || this.host.machine.stateDir) }
  }
  /** The branch of a Ticket's worktree, rendered from the branch template. */
  branchOf(ticket: Ticket, settings: Settings = this.host.store.settings()): string {
    return renderWorktree(settings.executor.worktrees.branch, this.names(ticket, settings))
  }
  /** The directory a Ticket's worktree stands in, rendered from the path template; undefined when the template leaves the root. */
  directoryOf(ticket: Ticket, settings: Settings = this.host.store.settings()): string | undefined {
    const rendered = renderWorktree(settings.executor.worktrees.path, this.names(ticket, settings))
    const path = resolve(isAbsolute(rendered) ? rendered : resolve(this.root(), rendered))
    return within(this.root(), path) ? path : undefined
  }
  /**
   * Creates `ticket`'s worktree at its directory, on its branch, from the base branch, then runs the create hook in it.
   * A branch the repository already has is checked out again when `reuse` holds, which is how a resumed Ticket finds its work.
   * @throws When there is no usable repository, the path template leaves the execution root, or git or the hook fails.
   */
  async create(ticket: Ticket, signal: AbortSignal = this.host.lifetime): Promise<{ path: string; branch: string; reused: boolean } | undefined> {
    const settings = this.host.store.settings(), config = this.config(settings)
    const worktrees = this.manager(settings)
    if (!worktrees) return undefined
    const path = this.directoryOf(ticket, settings)
    const branch = this.branchOf(ticket, settings)
    if (!path) throw new Error(`The worktree path template "${config.path}" leaves the execution root`)
    if (!await worktrees.usable(signal)) throw new Error(`The worktree repository ${config.repository} is not a git repository with a commit`)
    // A record of a worktree whose directory someone deleted would refuse the path; dropping it lets the checkout start again.
    if ((await worktrees.list(signal)).some(entry => resolve(entry.path) === resolve(path))) await worktrees.prune(signal)
    const base = config.base || await worktrees.defaultBranch(signal)
    await mkdir(dirname(path), { recursive: true })
    const created = await worktrees.create({ path, branch, base, reuse: config.reuse }, AbortSignal.any([signal, AbortSignal.timeout(GIT_MS)]))
    if (config.hooks.create.trim()) {
      await this.hook(ticket, config.hooks.create, created.path, CREATE_HOOK_MS, signal)
        .catch((error: unknown) => { throw new Error(`The create hook failed: ${error instanceof Error ? error.message : String(error)}`) })
    }
    return created
  }
  /** Runs one hook with `sh` in `cwd`, with the Ticket's execution variables in its environment. */
  private async hook(ticket: Ticket, command: string, cwd: string, timeoutMs: number, signal: AbortSignal): Promise<string> {
    const env = Object.fromEntries(this.host.environment(ticket).map(variable => [variable.key, variable.value]))
    return runAsWorker(this.host.subprocess, ['sh', '-c', command], cwd, AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]), env)
  }
  /** Every worktree of the repository, with the Ticket that works in it, its uncommitted paths and where its branch stands. */
  async list(signal: AbortSignal = this.host.lifetime): Promise<WorktreeRow[]> {
    const settings = this.host.store.settings(), config = this.config(settings)
    const worktrees = this.manager(settings)
    if (!worktrees) return []
    const base = config.base || await worktrees.defaultBranch(signal)
    const entries = await worktrees.list(AbortSignal.any([signal, AbortSignal.timeout(GIT_MS)]))
    const tickets = this.host.store.tickets.list()
    return Promise.all(entries.map(async entry => {
      const ticket = tickets.find(item => item.execution && resolve(item.execution.directory) === resolve(entry.path))
      const state = await worktrees.state(entry, base, signal).catch(() => ({ dirty: 0, ahead: 0, behind: 0 }))
      // Only a worktree below this deployment's root, on a branch, is one a sweep could remove, so only its merge state is worth the checks.
      const merged = within(this.root(), entry.path) && entry.branch ? await worktrees.addsNothing(entry.branch, base, signal).catch(() => false) : false
      return { path: entry.path, ...entry.branch ? { branch: entry.branch } : {}, ...entry.head ? { head: entry.head } : {},
        detached: entry.detached, ...entry.prunable ? { prunable: entry.prunable } : {}, ...state, merged,
        ...ticket ? { ticket: { id: ticket.id, title: ticket.title, open: !ticket.ended } } : {} }
    }))
  }
  /**
   * Removes the worktrees of Tickets that ended, whose branch would add nothing to the base branch and which hold no uncommitted
   * path: it runs each worktree's remove hook first, and drops the branch with the worktree when `deleteBranch` holds. Then it
   * drops the records of worktrees whose directories are gone, and records the sweep for the panel.
   * @throws When the repository cannot be read, which leaves the sweep unrecorded.
   */
  sweep(signal: AbortSignal = this.host.lifetime): Promise<WorktreeSweep | undefined> {
    return this.sweeping ??= this.sweepOnce(signal).finally(() => { this.sweeping = undefined })
  }
  private async sweepOnce(signal: AbortSignal): Promise<WorktreeSweep | undefined> {
    const settings = this.host.store.settings(), config = this.config(settings)
    const worktrees = this.manager(settings)
    if (!worktrees || config.cleanup === 'off' || signal.aborted) return undefined
    const entries = await worktrees.list(AbortSignal.any([signal, AbortSignal.timeout(GIT_MS)]))
    const root = this.root()
    const ended = this.host.store.tickets.list().filter(ticket => ticket.ended && ticket.execution)
    const report: WorktreeSweep = { at: new Date().toISOString(), removed: [], kept: [], pruned: 0 }
    const base = config.base || await worktrees.defaultBranch(signal)
    for (const entry of entries) {
      if (signal.aborted) break
      const ticket = within(root, entry.path) ? ended.find(item => item.execution && resolve(item.execution.directory) === resolve(entry.path)) : undefined
      // A worktree of this root that no ended Ticket names may be a Ticket's still, or a person's: it stays.
      if (!ticket) continue
      const branch = entry.branch ?? this.branchOf(ticket, settings)
      const keep = (reason: string) => { report.kept.push({ path: entry.path, branch, ticket: ticket.id, reason }) }
      // A detached worktree's commits need not reach any branch, so removing it could leave work of a Ticket unreachable.
      if (entry.detached || !entry.branch) { keep('it is detached'); continue }
      const state = await worktrees.state(entry, base, signal).catch(() => undefined)
      if (!state) { keep('its state could not be read'); continue }
      if (state.dirty > 0) { keep(`${state.dirty} uncommitted path${state.dirty === 1 ? '' : 's'}`); continue }
      const merged = await worktrees.addsNothing(entry.branch, base, signal).catch(() => false)
      if (!merged) { keep(`the branch adds changes to ${base}`); continue }
      try {
        if (config.hooks.remove.trim() && entry.branch === this.branchOf(ticket, settings)) await this.hook(ticket, config.hooks.remove, entry.path, REMOVE_HOOK_MS, signal)
        const result = await worktrees.remove({ path: entry.path, branch: entry.branch, base, deleteBranch: config.deleteBranch }, signal)
        if (!result.removed) { keep(result.kept ?? 'git kept it'); continue }
        report.removed.push({ path: entry.path, branch: result.branch, ticket: ticket.id })
        if (result.branchDeleted === false) report.kept.push({ path: entry.path, branch: result.branch, ticket: ticket.id,
          reason: `the worktree went and the branch stayed: ${result.branchKept ?? 'git kept it'}` })
      } catch (error) { keep(error instanceof Error ? error.message : String(error)) }
    }
    report.pruned = await worktrees.prune(signal).catch(() => 0)
    this.host.store.set(KV.worktrees.sweep, report)
    return report
  }
  /** The last sweep this deployment recorded, as the panel and the tool show it. */
  lastSweep(): WorktreeSweep | undefined { return this.host.store.get(KV.worktrees.sweep) }
  /**
   * Removes one worktree, named by its branch, its path or its directory's name, and its branch when that adds nothing to the base.
   * A worktree of an open Ticket is refused, since its worker may still write there, and so is one whose directory holds
   * uncommitted paths unless `force`.
   * @throws When this deployment has no repository, no such worktree exists, or the worktree belongs to an open Ticket.
   */
  async remove(target: string, input: { force?: boolean } = {}, signal: AbortSignal = this.host.lifetime): Promise<WorktreeRemoval> {
    const settings = this.host.store.settings(), config = this.config(settings)
    const worktrees = this.manager(settings)
    if (!worktrees) throw new Error('This deployment has no worktree repository; set it in the Execution settings')
    const entries = await worktrees.list(AbortSignal.any([signal, AbortSignal.timeout(GIT_MS)]))
    const entry = entries.find(candidate => candidate.branch === target || resolve(candidate.path) === resolve(target) || candidate.path.endsWith(`/${target}`))
    if (!entry) throw new Error(`No worktree of ${config.repository} is ${target}`)
    const open = this.host.store.tickets.list().find(item => !item.ended && item.execution && resolve(item.execution.directory) === resolve(entry.path))
    if (open) throw new Error(`${entry.path} is the worktree of the open Ticket ${open.id}; stop or finish it first`)
    const base = config.base || await worktrees.defaultBranch(signal)
    const ticket = this.host.store.tickets.list().find(item => item.execution && resolve(item.execution.directory) === resolve(entry.path))
    // The remove hook is a Ticket's, and runs where its worker's own work can still be read.
    if (config.hooks.remove.trim() && ticket && entry.branch === this.branchOf(ticket, settings)) await this.hook(ticket, config.hooks.remove, entry.path, REMOVE_HOOK_MS, signal)
    const result = await worktrees.remove({ path: entry.path, branch: entry.branch, base, force: input.force, deleteBranch: config.deleteBranch }, signal)
    return { path: entry.path, ...entry.branch ? { branch: entry.branch } : {}, removed: result.removed, ...result.branchDeleted !== undefined ? { branchDeleted: result.branchDeleted } : {},
      ...result.kept ? { reason: result.kept } : !result.removed && result.branchKept ? { reason: `the branch stayed: ${result.branchKept}` } : {} }
  }
  /** Drops the records of worktrees whose directories are gone, and reports how many. */
  async prune(signal: AbortSignal = this.host.lifetime): Promise<number> {
    const worktrees = this.manager()
    return worktrees ? worktrees.prune(signal) : 0
  }
}
