/**
 * The nuclear side of this agent: which kit this installation runs, and each Ticket's seven-stage state as the kit's
 * own command line reports it. The service caches a workspace scan for a short while so the panel can poll it without
 * starting a Python process per request, and forgets a scan when a person asks for a fresh one.
 */
import { execFile } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import type { Ticket } from '../core/index.ts'
import { isWorkspace, kitProblem, NUCLEAR_DEFAULTS, reportIn, scanWorkspace, type NuclearIo,
  type NuclearSettings, type NuclearSnapshot, type NuclearStage, type SnapshotProblem } from '../nuclear/index.ts'

/** How much of an approval or project file is read: both are small, and a scan must not read a large file by accident. */
const READ_LIMIT = 256 * 1024

export const readOf = (path: string): string | undefined => {
  try {
    if (!statSync(path).isFile() || statSync(path).size > READ_LIMIT) return undefined
    return readFileSync(path, 'utf8')
  } catch { return undefined /* A missing or unreadable file is reported by the scan as absent. */ }
}

/** Run one kit command with the host's own PATH, without a shell, and with both streams captured. */
const runner: NuclearIo['run'] = (argv, { timeoutMs, signal }) => new Promise(resolve => {
  execFile(argv[0]!, argv.slice(1), { timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024, signal, windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' } },
  (error, stdout, stderr) => resolve({ code: error && 'code' in error && typeof error.code === 'number' ? error.code : error ? null : 0,
    stdout: String(stdout), stderr: String(stderr) }))
})

export interface NuclearKit { ready: boolean; problem?: SnapshotProblem; pythonVersion?: string }

export interface NuclearHost {
  readonly settings: NuclearSettings
  /** Aborted when the host stops, so a scan in flight does not outlive it. */
  readonly lifetime: AbortSignal
}

/** One Ticket's workspace as the panel shows it: the Ticket's short name, where it works, and the scan. */
export interface NuclearProject {
  root: string
  tickets: { id: string; title: string }[]
  snapshot: NuclearSnapshot
}

/**
 * Reads each Ticket directory's nuclear state through the kit's command line, keeping one scan per directory for a few
 * seconds. It judges nothing itself: every stage verdict and every message comes from `nuclearlib.py`.
 */
export class Nuclear {
  private readonly cache = new Map<string, { at: number; snapshot: NuclearSnapshot }>()
  private readonly inflight = new Map<string, Promise<NuclearSnapshot>>()
  private pythonVersion?: string
  private pythonError?: string
  private probed = false
  constructor(private readonly host: NuclearHost) {}
  get settings(): NuclearSettings { return { ...NUCLEAR_DEFAULTS, ...this.host.settings } }
  /** Whether this installation is pointed at a kit at all; while it is not, the flow is simply absent. */
  configured(): boolean { return !!this.settings.kitPath }
  /** The kit's state for the panel: whether both of its scripts are where the deployment says, and the interpreter. */
  kit(): NuclearKit {
    const problem = kitProblem(this.settings, existsSync)
    return { ready: !problem, ...problem ? { problem } : {},
      ...this.pythonVersion ? { pythonVersion: this.pythonVersion } : {} }
  }
  /** Ask the configured interpreter for its version once, so the panel can show why a scan would fail before one does. */
  async probe(): Promise<void> {
    if (this.probed || !this.configured()) return
    this.probed = true
    const result = await runner([this.settings.python, '--version'], { timeoutMs: Math.min(this.settings.timeoutMs, 10_000) })
      .catch(error => ({ code: null, stdout: '', stderr: String(error) }))
    const text = `${result.stdout}${result.stderr}`.trim()
    if (result.code === 0 && text) this.pythonVersion = text
    else this.pythonError = text || `exit code ${result.code}`
  }
  /** The interpreter's failure as the panel words it, when `python --version` did not answer. */
  get interpreterProblem(): SnapshotProblem | undefined {
    return this.pythonError ? { code: 'tool-failed',
      detail: `The configured interpreter "${this.settings.python}" did not answer: ${this.pythonError}` } : undefined
  }
  /** Drop every cached scan, so the next read asks the kit again. */
  forget(): void { this.cache.clear() }
  /** Read one workspace, from the cache while it is fresh and from the kit otherwise; concurrent reads share one scan. */
  async snapshot(root: string, options: { fresh?: boolean } = {}): Promise<NuclearSnapshot> {
    const cached = this.cache.get(root)
    const ttl = Math.max(this.settings.refreshSeconds, 1) * 1000
    if (!options.fresh && cached && Date.now() - cached.at < ttl) return cached.snapshot
    const running = this.inflight.get(root)
    if (running && !options.fresh) return running
    const scan = scanWorkspace(root, this.settings, { exists: existsSync, read: readOf, run: runner }, this.host.lifetime)
    this.inflight.set(root, scan)
    try {
      const snapshot = await scan
      this.cache.set(root, { at: Date.now(), snapshot })
      return snapshot
    } finally { this.inflight.delete(root) }
  }
  /**
   * The kit's own verdict on one stage of a Ticket's workspace, read afresh because a stage agent has just written it, or
   * nothing when the Ticket has no workspace the kit knows or no kit is configured: `passed`, with the kit's errors.
   * This agent words none of them and decides nothing here.
   */
  async stageVerdict(ticket: Ticket, stage: NuclearStage): Promise<{ passed: boolean; errors: string[] } | undefined> {
    const root = ticket.execution?.directory
    if (!this.configured() || !root || !existsSync(root) || !isWorkspace(root, existsSync)) return undefined
    const report = reportIn(await this.snapshot(root, { fresh: true }), stage)
    return report ? { passed: report.passed, errors: report.errors } : undefined
  }
  /**
   * The nuclear state of one Ticket's directory, or nothing when the Ticket has none yet: its Executor may not have
   * started, or its directory may be an ordinary working copy without a kit workspace.
   */
  async ticketSnapshot(ticket: Ticket): Promise<NuclearSnapshot | undefined> {
    const root = ticket.execution?.directory
    if (!this.configured() || !root || !existsSync(root) || !isWorkspace(root, existsSync)) return undefined
    return this.snapshot(root)
  }
  /**
   * The workspaces of the given Tickets, one scan per distinct directory and at most `maxProjects` of them, newest
   * Tickets first, so a panel with many Tickets still answers within one poll. `omitted` counts the workspaces the
   * cap left unscanned, which the panel says rather than showing a board that looks complete.
   */
  async board(tickets: readonly Ticket[]): Promise<{ projects: NuclearProject[]; omitted: number }> {
    if (!this.configured()) return { projects: [], omitted: 0 }
    const byRoot = new Map<string, NuclearProject>()
    let omitted = 0
    for (const ticket of tickets) {
      const root = ticket.execution?.directory
      if (!root || !existsSync(root) || !isWorkspace(root, existsSync)) continue
      const project = byRoot.get(root)
      const entry = { id: ticket.id, title: ticket.title }
      if (project) { project.tickets.push(entry); continue }
      if (byRoot.size >= Math.max(this.settings.maxProjects, 1)) { omitted += 1; continue }
      byRoot.set(root, { root, tickets: [entry], snapshot: { root, checkedAt: '', stages: [] } })
    }
    const roots = [...byRoot.keys()]
    const snapshots = await Promise.all(roots.map(root => this.snapshot(root)))
    roots.forEach((root, index) => { byRoot.get(root)!.snapshot = snapshots[index]! })
    return { projects: [...byRoot.values()], omitted }
  }
}

