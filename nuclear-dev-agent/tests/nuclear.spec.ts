/**
 * The nuclear bridge: how a stage's state follows from the kit's status, its artifact and its approval file; what the
 * bridge runs; what it does with a kit that is missing, that fails or that answers no JSON; the scan cache, a Ticket's
 * board, and the views the panel and the overview read.
 */
import { execFileSync } from 'node:child_process'
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Ticket } from '../src/core/index.ts'
import { Nuclear } from '../src/app/nuclear.ts'
import { nuclearView, overviewNuclear, ticketNuclearView } from '../src/app/views/nuclear.ts'
import { NUCLEAR_DEFAULTS, NUCLEAR_STAGES, STAGE_ARTIFACTS, classifyStage, controlScript, gateArgv, isWorkspace, kitProblem,
  scanWorkspace, stageReport, statusArgv, type CommandResult, type NuclearIo, type NuclearSettings, type NuclearSnapshot }
  from '../src/nuclear/index.ts'

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
let directory: string
beforeEach(() => { directory = mkdtempSync(join(tmpdir(), 'nuclear-dev-agent-nuclear-')) })
afterEach(() => { rmSync(directory, { recursive: true, force: true }) })

const settings = (kitPath: string, over: Partial<NuclearSettings> = {}): NuclearSettings =>
  ({ ...NUCLEAR_DEFAULTS, kitPath, timeoutMs: 20_000, ...over })

/** A kit on disk: the two scripts the bridge insists on, without which nothing is run. */
function kit(path = kitPath()): string {
  mkdirSync(join(path, 'skills', 'nuclear-dev', 'scripts'), { recursive: true })
  for (const name of ['nuclearctl.py', 'nuclearlib.py']) writeFileSync(join(path, 'skills', 'nuclear-dev', 'scripts', name), '')
  return path
}
const kitPath = () => join(directory, 'kit')
/** A workspace on disk, as the kit writes it: `project.json` marks it as one. */
function workspace(path = join(directory, 'work')): string {
  mkdirSync(join(path, '.nuclear-dev'), { recursive: true })
  writeFileSync(join(path, '.nuclear-dev', 'project.json'), JSON.stringify({ name: '示范求解器', project_id: 'demo',
    kit_version: '0.1.0', safety_classification: 'B', vv_level: '2' }))
  return path
}
const status = (stages: Record<string, { passed: boolean; errors?: string[] }>): string => JSON.stringify({ command: 'status', ok: true,
  stages: Object.fromEntries(Object.entries(stages).map(([stage, value]) => [stage, { passed: value.passed, errors: value.errors ?? [] }])) })
const gate = (stage: string, errors: string[]): string => JSON.stringify({ command: 'gate', ok: !errors.length, stage, errors })

/** An I/O double: the files the scan may see, and the answers the kit's command line gives, recorded by argv. */
function fake(files: Record<string, string>, answers: (argv: string[]) => CommandResult) {
  const calls: string[][] = []
  const io: NuclearIo = { exists: path => Object.hasOwn(files, path), read: path => files[path], run: async argv => {
    calls.push(argv)
    return answers(argv)
  } }
  return { io, calls }
}
const answered = (stdout: string, code = 0): CommandResult => ({ code, stdout, stderr: '' })

describe('a stage\'s state', () => {
  it('follows the kit\'s verdict, then whether its artifact exists, then whether only a signature is missing', () => {
    expect(classifyStage({ passed: true, present: true, errors: [] })).toBe('passed')
    // No artifact: the work has not started, whatever else the kit reports.
    expect(classifyStage({ passed: false, present: false, errors: ['缺少阶段产物: stages/plan/plan.json'] })).toBe('missing')
    // Only approval defects: a person has to sign, and the agent must not.
    expect(classifyStage({ passed: false, present: true, errors: ['缺少人工批准记录: approvals/plan.json'] })).toBe('awaiting-approval')
    expect(classifyStage({ passed: false, present: true, errors: ['approval.scope: 必须包含当前阶段产物 stages/plan/plan.json',
      'approval.artifact_sha256: 产物已变化，批准失效'] })).toBe('awaiting-approval')
    // An artifact or evidence defect is the work's own, even beside an approval one.
    expect(classifyStage({ passed: false, present: true, errors: ['approval.scope: 缺少', 'evidence.index: 证据未登记'] })).toBe('blocked')
    expect(classifyStage({ passed: false, present: true, errors: [] })).toBe('blocked')
  })

  it('names the artifact the kit names, and keeps the kit\'s messages as written', () => {
    const report = stageReport('vv', { passed: false, present: true, errors: ['approval.approver: V&V 最终批准人不能来自开发组织'] })
    expect(report).toEqual({ stage: 'vv', artifact: 'stages/vv/vv-report.json', present: true, passed: false, state: 'awaiting-approval',
      errors: ['approval.approver: V&V 最终批准人不能来自开发组织'] })
  })
})

describe('the kit this installation runs', () => {
  it('refuses to guess: no configured kit, or one without both of its scripts, is reported rather than run', () => {
    expect(kitProblem({ kitPath: '' }, () => true)).toMatchObject({ code: 'kit-missing' })
    expect(kitProblem({ kitPath: '/srv/kit' }, path => !path.endsWith('nuclearlib.py'))).toMatchObject({ code: 'kit-missing',
      detail: expect.stringContaining('nuclearlib.py') })
    expect(kitProblem({ kitPath: '/srv/kit' }, () => true)).toBeUndefined()
  })

  it('runs the gate command line with --root before the subcommand, as the kit\'s help requires', () => {
    const options = { python: '/usr/bin/python3', kitPath: '/srv/kit' }
    expect(statusArgv(options, '/w/t1')).toEqual(['/usr/bin/python3', controlScript('/srv/kit'), '--root', '/w/t1', 'status', '--json'])
    expect(gateArgv(options, '/w/t1', 'design')).toEqual(['/usr/bin/python3', controlScript('/srv/kit'), '--root', '/w/t1', 'gate',
      'design', '--json'])
  })

  it('recognizes a workspace by the kit\'s own project file', () => {
    expect(isWorkspace('/w/t1', path => path === join('/w/t1', '.nuclear-dev', 'project.json'))).toBe(true)
    expect(isWorkspace('/w/t1', () => false)).toBe(false)
  })
})

describe('scanning one workspace', () => {
  it('reads every stage, the approval file and the gate of the stage the work stands on', async () => {
    const root = '/w/t1', path = kit(resolveKit())
    const plan = join(root, '.nuclear-dev', STAGE_ARTIFACTS.plan)
    const { io, calls } = fake({ [join(path, 'skills/nuclear-dev/scripts/nuclearctl.py')]: '',
      [join(path, 'skills/nuclear-dev/scripts/nuclearlib.py')]: '', [plan]: '{}',
      [join(root, '.nuclear-dev', 'project.json')]: JSON.stringify({ name: '求解器', project_id: 'demo', kit_version: '0.1.0' }) },
    argv => argv.includes('status')
      ? answered(status({ plan: { passed: false, errors: ['缺少人工批准记录: approvals/plan.json'] } }))
      : answered(gate(argv[argv.length - 2]!, ['缺少人工批准记录: approvals/plan.json']), 1))
    const snapshot = await scanWorkspace(root, settings(path), io)
    expect(snapshot.problem).toBeUndefined()
    expect(snapshot.stages.map(stage => stage.stage)).toEqual([...NUCLEAR_STAGES])
    expect(snapshot.stages[0]).toMatchObject({ stage: 'plan', present: true, state: 'awaiting-approval' })
    expect(snapshot.stages[1]).toMatchObject({ stage: 'requirements', present: false, state: 'missing' })
    expect(snapshot.next).toBe('plan')
    expect(snapshot.gate).toEqual({ stage: 'plan', ok: false, errors: ['缺少人工批准记录: approvals/plan.json'] })
    expect(snapshot.project).toMatchObject({ name: '求解器', id: 'demo', kitVersion: '0.1.0' })
    // The status ran once, then the gate once, for the stage the work stands on.
    expect(calls).toHaveLength(2)
    expect(calls[0]).toEqual(statusArgv({ python: 'python3', kitPath: path }, root))
    expect(calls[1]).toEqual(gateArgv({ python: 'python3', kitPath: path }, root, 'plan'))
  })

  it('reads the approval a stage records, with the name a person signed it under', async () => {
    const root = '/w/t1', path = kit(resolveKit())
    const { io } = fake({ [join(path, 'skills/nuclear-dev/scripts/nuclearctl.py')]: '',
      [join(path, 'skills/nuclear-dev/scripts/nuclearlib.py')]: '',
      [join(root, '.nuclear-dev', STAGE_ARTIFACTS.plan)]: '{}',
      [join(root, '.nuclear-dev', 'approvals', 'plan.json')]: JSON.stringify({ decision: 'approved', date: '2026-11-01T00:00:00Z',
        approver: { name: '张工', role: '审核人', organization: '某设计院' } }) },
    // Every stage passed, so the scan runs no gate and nothing it reports stands in the way.
    argv => answered(status(Object.fromEntries(NUCLEAR_STAGES.map(stage => [stage, { passed: true }])))))
    const snapshot = await scanWorkspace(root, settings(path), io)
    expect(snapshot.stages[0]!.approval).toEqual({ approver: '张工', role: '审核人', organization: '某设计院', decision: 'approved',
      date: '2026-11-01T00:00:00Z' })
    // Every stage passed, so no gate ran: nothing stands in the way.
    expect(snapshot.next).toBeUndefined()
    expect(snapshot.gate).toBeUndefined()
  })

  it('reports a kit that is absent or that answers no JSON instead of an empty board', async () => {
    const missing = await scanWorkspace('/w/t1', settings(''), fake({}, () => answered('', 127)).io)
    expect(missing).toMatchObject({ stages: [], problem: { code: 'kit-missing' } })
    const path = kit(resolveKit())
    const broken = await scanWorkspace('/w/t1', settings(path), fake({ [join(path, 'skills/nuclear-dev/scripts/nuclearctl.py')]: '',
      [join(path, 'skills/nuclear-dev/scripts/nuclearlib.py')]: '' },
    () => ({ code: 2, stdout: '', stderr: 'Traceback: no such option' })).io)
    expect(broken).toMatchObject({ stages: [], problem: { code: 'tool-failed', detail: expect.stringContaining('no such option') } })
  })
})

describe('the service the host reads', () => {
  const requestCounter = () => join(directory, 'runs')

  /** A kit whose command line counts its runs, so the cache is observable. */
  function countingKit(): string {
    const path = kit(join(directory, 'counting-kit'))
    const script = join(path, 'skills', 'nuclear-dev', 'scripts', 'nuclearctl.py')
    writeFileSync(script, ['#!/usr/bin/env python3', 'import json, pathlib, sys',
      `counter = pathlib.Path(${JSON.stringify(requestCounter())})`,
      // Only the status run counts, so a scan is one run however many stages the gate is asked about.',
      'if "status" in sys.argv:',
      '    counter.write_text(str(int(counter.read_text() or 0) + 1) if counter.exists() else "1")',
      'if "status" in sys.argv:',
      '    print(json.dumps({"ok": True, "stages": {stage: {"passed": False, "errors": ["缺少阶段产物"]} for stage in',
      '      ["plan", "requirements", "design", "implementation", "test", "vv", "release"]}}))',
      'else:',
      '    print(json.dumps({"ok": False, "stage": sys.argv[-2], "errors": ["缺少阶段产物"]}))'].join('\n'))
    chmodSync(script, 0o755)
    return path
  }
  const runs = () => Number(readFileSync(requestCounter(), 'utf8'))
  const ticket = (id: string, path: string | undefined) => ({ id, title: `票据 ${id}`,
    execution: path ? { name: id, directory: path } : undefined } as unknown as Ticket)

  it('keeps one scan per directory for the refresh window, and forgets it when a person asks', async () => {
    const path = countingKit(), root = workspace()
    const service = new Nuclear({ settings: settings(path), lifetime: new AbortController().signal })
    expect(service.configured()).toBe(true)
    const first = await service.snapshot(root)
    expect(first.stages).toHaveLength(7)
    expect(runs()).toBe(1)
    // Within the window the cached scan answers, so a polling panel starts no process.
    expect(await service.snapshot(root)).toBe(first)
    expect(runs()).toBe(1)
    // A fresh read asks the kit again, and so does a read after the cache is dropped.
    await service.snapshot(root, { fresh: true })
    expect(runs()).toBe(2)
    service.forget()
    await service.snapshot(root)
    expect(runs()).toBe(3)
  })

  it('reads a Ticket\'s directory only when it holds a kit workspace, and groups Tickets by directory', async () => {
    const path = countingKit(), root = workspace(), plain = join(directory, 'plain')
    mkdirSync(plain, { recursive: true })
    const service = new Nuclear({ settings: settings(path, { maxProjects: 1, refreshSeconds: 30 }), lifetime: new AbortController().signal })
    expect(await service.ticketSnapshot(ticket('t0', plain))).toBeUndefined()
    expect(await service.ticketSnapshot(ticket('t0', undefined))).toBeUndefined()
    expect((await service.ticketSnapshot(ticket('t1', root)))?.stages).toHaveLength(7)
    // Two Tickets of one directory share one board, and the cap bounds how many directories one refresh scans.
    const board = await service.board([ticket('t1', root), ticket('t2', root), ticket('t3', workspace(join(directory, 'other')))])
    expect(board.projects).toHaveLength(1)
    expect(board.projects[0]!.tickets.map(item => item.id)).toEqual(['t1', 't2'])
    // The cap is reported rather than silently shortening the board.
    expect(board.omitted).toBe(1)
  })

  it('switches the flow off when the deployment names no kit, and reports the interpreter it would use', async () => {
    const off = new Nuclear({ settings: settings(''), lifetime: new AbortController().signal })
    expect(off.configured()).toBe(false)
    expect(off.kit()).toMatchObject({ ready: false, problem: { code: 'kit-missing' } })
    expect(await off.board([])).toEqual({ projects: [], omitted: 0 })
    const on = new Nuclear({ settings: settings(kit(resolveKit()), { python: process.env.PYTHON ?? 'python3' }),
      lifetime: new AbortController().signal })
    await on.probe()
    expect(on.kit()).toMatchObject({ ready: true, pythonVersion: expect.stringMatching(/^Python 3\./) })
  })
})

describe('the views', () => {
  const snapshotOf = (stages: { passed: boolean; present: boolean; state: NuclearSnapshot['stages'][number]['state']; errors?: string[] }[]): NuclearSnapshot => ({
    root: '/w/t1', checkedAt: '2026-11-05T00:00:00Z',
    stages: stages.map((stage, index) => stageReport(NUCLEAR_STAGES[index]!, { passed: stage.passed, present: stage.present,
      errors: stage.errors ?? [] })),
    ...stages.some(stage => !stage.passed) ? { next: NUCLEAR_STAGES[stages.findIndex(stage => !stage.passed)] } : {} })

  it('counts the stages of every workspace and lists the one a person or the work must take up', () => {
    const passed = snapshotOf(NUCLEAR_STAGES.map(() => ({ passed: true, present: true, state: 'passed' as const })))
    const waiting = snapshotOf([{ passed: true, present: true, state: 'passed' },
      { passed: false, present: true, state: 'awaiting-approval', errors: ['缺少人工批准记录: approvals/requirements.json'] },
      ...NUCLEAR_STAGES.slice(2).map(() => ({ passed: false, present: false, state: 'missing' as const }))])
    const projects = [{ root: '/w/t1', tickets: [{ id: 't1', title: '票据 t1' }], snapshot: waiting },
      { root: '/w/t2', tickets: [], snapshot: passed }]
    const view = nuclearView({ settings: settings('/srv/kit'), kit: { ready: true, pythonVersion: 'Python 3.12.3' }, projects })
    expect(view.configured).toBe(true)
    expect(view.header).toMatchObject({ kitPath: '/srv/kit', ready: true, pythonVersion: 'Python 3.12.3' })
    expect(view.counts).toEqual({ projects: 2, passed: 8, awaiting: 1, blocked: 0, missing: 5, complete: 1 })
    expect(view.projects[0]).toMatchObject({ passed: 1, complete: false, attention: 'requirements' })
    expect(view.projects[1]).toMatchObject({ passed: 7, complete: true, attention: undefined })
    const overview = overviewNuclear(projects)
    expect(overview.attention).toEqual([{ root: '/w/t1', tickets: [{ id: 't1', title: '票据 t1' }], stage: 'requirements',
      state: 'awaiting-approval', errors: ['缺少人工批准记录: approvals/requirements.json'] }])
    // A Ticket's section carries the same rows and the gate, without the workspace's other Tickets.
    expect(ticketNuclearView(waiting)).toMatchObject({ passed: 1, next: 'requirements', attention: 'requirements' })
  })
})

describe.runIf(python())('a real kit', () => {
  it('reads a workspace the kit itself initialized, and stops at the first stage that has no artifact', async () => {
    const root = join(directory, 'project')
    mkdirSync(root, { recursive: true })
    execFileSync(python()!, [controlScript(REPO), '--root', root, 'init', '--name', '示例核能软件', '--id', 'demo', '--json'],
      { encoding: 'utf8' })
    const snapshot = await scanWorkspace(root, settings(REPO, { python: python()! }), {
      exists: path => existsSync(path), read: path => { try { return readFileSync(path, 'utf8') } catch { return undefined } },
      run: async (argv, options) => {
        try { return { code: 0, stdout: execFileSync(argv[0]!, argv.slice(1), { encoding: 'utf8', timeout: options.timeoutMs }), stderr: '' } }
        catch (error) { const failure = error as { status?: number; stdout?: string; stderr?: string }
          return { code: failure.status ?? null, stdout: failure.stdout ?? '', stderr: failure.stderr ?? '' } }
      } })
    expect(snapshot.problem).toBeUndefined()
    expect(snapshot.project).toMatchObject({ name: '示例核能软件', id: 'demo' })
    expect(snapshot.stages.map(stage => stage.state)).toEqual(NUCLEAR_STAGES.map(() => 'missing'))
    expect(snapshot.next).toBe('plan')
    expect(snapshot.gate?.ok).toBe(false)
    expect(snapshot.gate?.errors.join('\n')).toContain('缺少阶段产物')
  })
})

/** A kit directory of its own for a case that only needs the scripts to exist. */
const resolveKit = () => join(directory, 'kit')
/** The interpreter the deployment would run, when this machine has one. */
function python(): string | undefined {
  for (const name of [process.env.PYTHON, 'python3', 'python']) {
    if (!name) continue
    try { execFileSync(name, ['--version'], { stdio: 'ignore' }); return name } catch { /* try the next name */ }
  }
  return undefined
}
