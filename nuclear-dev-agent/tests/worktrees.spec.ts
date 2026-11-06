/** The Ticket worktree lifecycle against real git repositories: creation, reuse, the checks that guard a removal, the sweep, and hooks. */
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, expect, it } from 'vitest'
import type { SubprocessOutputReader } from '@deepseek-ai/dsh-subprocess'
import { Store } from '../src/app/store.ts'
import type { Ticket } from '../src/core/index.ts'
import { KV } from '../src/kv.ts'
import { SettingsSchema } from '../src/policy.ts'
import { TicketWorktrees } from '../src/executor/worktrees.ts'
import { gitEnv } from './fixtures/git.ts'
import { Worktrees, gitRun, parseWorktrees, renderWorktree, within, worktreePath } from '../src/infra/worktrees.ts'

let root: string, repository: string
/** The environment of the test's git processes: the agent's own git configuration, with an identity to commit as. */
const base = (extra: Record<string, string> = {}): Record<string, string> => ({ ...gitEnv(extra), GIT_AUTHOR_NAME: 'Test',
  GIT_AUTHOR_EMAIL: 'test@example.com', GIT_COMMITTER_NAME: 'Test', GIT_COMMITTER_EMAIL: 'test@example.com' } as Record<string, string>)
/** A subprocess runtime that really runs what it is given, so a hook and a git command behave as they do for a worker. */
const realSubprocess = { spawn: (spec: { argv: readonly string[]; cwd: string; env?: Record<string, string> }) => {
  const child = spawn(spec.argv[0]!, [...spec.argv.slice(1)], { cwd: spec.cwd,
    env: base(spec.env ?? {}) })
  let stdout = '', stderr = ''
  child.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString() })
  child.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString() })
  child.on('error', () => { /* The command could not start, which its exit status reports. */ })
  const done = new Promise<{ exitCode: number | null; signal: null }>(settle => { child.on('close', code => { settle({ exitCode: code ?? 1, signal: null }) })
    child.on('error', () => { settle({ exitCode: 1, signal: null }) }) })
  const reader = (text: () => string): SubprocessOutputReader => ({ readFrom: () => ({ text: text(), nextOffset: text().length, lossy: false }) })
  return { done, collected: { stdout: reader(() => stdout), stderr: reader(() => stderr) } }
} }
const git = (...args: string[]): string => execFileSync('git', args, { cwd: repository, env: base() }).toString()
const commit = (message: string, file = 'file.txt', text = message): void => {
  writeFileSync(join(repository, file), `${text}\n`)
  git('add', '-A')
  git('commit', '-q', '-m', message)
}
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'nuclear-dev-worktrees-'))
  repository = join(root, 'widgets')
  mkdirSync(repository, { recursive: true })
  execFileSync('git', ['init', '-q', '--initial-branch=main'], { cwd: repository, env: base() })
  commit('first')
})
afterEach(() => { rmSync(root, { recursive: true, force: true }) })

it('renders a Ticket\'s path and branch from templates, and reads a path below the execution root only', () => {
  const names = { name: 'fix-copy-1234', ticket: 't123', repo: 'widgets' }
  expect(renderWorktree('{repo}/{name}', names)).toBe('widgets/fix-copy-1234')
  expect(renderWorktree('agent/{name}', names)).toBe('agent/fix-copy-1234')
  expect(renderWorktree('{ticket}-{name}', names)).toBe('t123-fix-copy-1234')
  expect(worktreePath('/state/work', '{name}', names)).toBe('/state/work/fix-copy-1234')
  expect(worktreePath('/state/work', '/elsewhere/{name}', names)).toBeUndefined()
  expect(worktreePath('/state/work', '../{name}', names)).toBeUndefined()
  expect(within('/state/work', '/state/work/a')).toBe(true)
  expect(within('/state/work', '/state/work')).toBe(true)
  expect(within('/state/work', '/state/workish/a')).toBe(false)
})

it('parses the porcelain listing, including a worktree git would prune and a detached one', () => {
  const text = ['worktree /repo', 'HEAD 1111', 'branch refs/heads/main', '', 'worktree /repo.feature', 'HEAD 2222',
    'branch refs/heads/feature', '', 'worktree /repo.gone', 'HEAD 3333', 'detached', 'prunable gitdir file points to non-existent location', ''].join('\n')
  expect(parseWorktrees(text)).toEqual([
    { path: '/repo', head: '1111', branch: 'main', bare: false, detached: false },
    { path: '/repo.feature', head: '2222', branch: 'feature', bare: false, detached: false },
    { path: '/repo.gone', head: '3333', bare: false, detached: true, prunable: 'gitdir file points to non-existent location' },
  ])
})

it('creates a worktree from the base branch, reads its state, and removes it with its branch once the branch is merged', async () => {
  const worktrees = new Worktrees(gitRun(realSubprocess as never), repository)
  const path = join(root, 'work', 'feature')
  const created = await worktrees.create({ path, branch: 'agent/feature', base: 'main' })
  expect(created).toEqual({ path, branch: 'agent/feature', reused: false })
  expect(existsSync(join(path, 'file.txt'))).toBe(true)
  expect((await worktrees.list()).map(entry => entry.branch).sort()).toEqual(['agent/feature', 'main'])
  expect(await worktrees.state({ path, branch: 'agent/feature' }, 'main')).toMatchObject({ dirty: 0, ahead: 0, behind: 0 })
  // Work in the worktree, until the branch adds something the base branch does not have.
  writeFileSync(join(path, 'second.txt'), 'second\n')
  execFileSync('git', ['add', '-A'], { cwd: path, env: base() })
  execFileSync('git', ['commit', '-q', '-m', 'second'], { cwd: path, env: base() })
  expect(await worktrees.state({ path, branch: 'agent/feature' }, 'main')).toMatchObject({ ahead: 1 })
  expect(await worktrees.addsNothing('agent/feature', 'main')).toBe(false)
  git('merge', '-q', '--ff-only', 'agent/feature')
  expect(await worktrees.addsNothing('agent/feature', 'main')).toBe(true)
  const removal = await worktrees.remove({ path, branch: 'agent/feature', base: 'main' })
  expect(removal).toMatchObject({ removed: true, branch: 'agent/feature', branchDeleted: true })
  expect(existsSync(path)).toBe(false)
  expect((await worktrees.list()).map(entry => entry.branch)).toEqual(['main'])
})

it('keeps a worktree with uncommitted paths, and a branch the base does not have, unless forced', async () => {
  const worktrees = new Worktrees(gitRun(realSubprocess as never), repository)
  const path = join(root, 'work', 'dirty')
  await worktrees.create({ path, branch: 'agent/dirty', base: 'main' })
  writeFileSync(join(path, 'unmerged.txt'), 'unmerged\n')
  execFileSync('git', ['add', '-A'], { cwd: path, env: base() })
  execFileSync('git', ['commit', '-q', '-m', 'unmerged'], { cwd: path, env: base() })
  writeFileSync(join(path, 'note.txt'), 'kept\n')
  expect(await worktrees.remove({ path, branch: 'agent/dirty', base: 'main' })).toMatchObject({ removed: false, kept: 'uncommitted changes' })
  expect(existsSync(path)).toBe(true)
  // A clean worktree whose branch is unmerged keeps the branch, and says so.
  rmSync(join(path, 'note.txt'))
  const unmerged = await worktrees.remove({ path, branch: 'agent/dirty', base: 'main' })
  expect(unmerged).toMatchObject({ removed: true, branchDeleted: false, branchKept: 'unmerged changes' })
  // The worktree is gone, and the branch that still holds its work is not.
  expect((await worktrees.list()).map(entry => entry.branch)).toEqual(['main'])
  expect(await worktrees.branch('agent/dirty')).toBe('agent/dirty')
  const forced = await worktrees.remove({ path: join(root, 'work', 'gone'), force: true })
  expect(forced).toMatchObject({ removed: false, kept: 'directory is not a worktree' })
})

it('checks out a branch the repository already has again, which is how a resumed Ticket finds its work', async () => {
  const worktrees = new Worktrees(gitRun(realSubprocess as never), repository)
  const first = join(root, 'work', 'resumed')
  await worktrees.create({ path: first, branch: 'agent/resumed', base: 'main' })
  writeFileSync(join(first, 'work.txt'), 'half done\n')
  execFileSync('git', ['add', '-A'], { cwd: first, env: base() })
  execFileSync('git', ['commit', '-q', '-m', 'work'], { cwd: first, env: base() })
  await worktrees.remove({ path: first, branch: 'agent/resumed', base: 'main', deleteBranch: false })
  const again = await worktrees.create({ path: first, branch: 'agent/resumed', base: 'main' })
  expect(again).toMatchObject({ path: first, branch: 'agent/resumed', reused: true })
  expect(existsSync(join(first, 'work.txt'))).toBe(true)
  await expect(worktrees.create({ path: join(root, 'work', 'other'), branch: 'agent/resumed', base: 'main', reuse: false }))
    .rejects.toThrow('The branch agent/resumed exists')
})

it('prunes the records of worktrees whose directories someone deleted', async () => {
  const worktrees = new Worktrees(gitRun(realSubprocess as never), repository)
  const path = join(root, 'work', 'lost')
  await worktrees.create({ path, branch: 'agent/lost', base: 'main' })
  rmSync(path, { recursive: true, force: true })
  expect((await worktrees.list()).some(entry => entry.path === path)).toBe(true)
  expect(await worktrees.prune()).toBe(1)
  expect((await worktrees.list()).some(entry => entry.path === path)).toBe(false)
})

/** A Ticket record with only what the worktree lifecycle reads. */
const ticketOf = (id: string, name: string): Ticket => ({ id, title: `Ticket ${id}`, decisionId: 'd', mandate: { strength: 'explicit', basis: {}, scope: '' },
  channels: [], assignments: [], inputs: [], undelivered: [], createdAt: '', updatedAt: '', origin: { triggerId: 't', triggerIds: ['t'] },
  execution: { name, directory: '', assignment: '' } } as unknown as Ticket)

it('creates a Ticket\'s worktree with its hook, sweeps the worktree of an ended Ticket once its work is in the base, and keeps a dirty one', async () => {
  const state = join(root, 'state')
  mkdirSync(state, { recursive: true })
  const store = new Store(join(state, 'state.sqlite'))
  const executor = store.settings().executor
  store.saveSettings({ ...store.settings(), executor: { ...executor, directory: join(root, 'work'),
    worktrees: { repository, path: '{name}', branch: 'agent/{name}', base: 'main', reuse: true, cleanup: 'safe', deleteBranch: true,
      hooks: { create: 'printf hooked > "$DSH_NUCLEAR_DEV_AGENT_DIR.hook"', remove: 'printf removed > "$DSH_NUCLEAR_DEV_AGENT_DIR.removed"' } } } })
  const worktrees = new TicketWorktrees({ subprocess: realSubprocess as never, store, machine: { stateDir: state }, lifetime: new AbortController().signal,
    environment: ticket => [{ key: 'DSH_NUCLEAR_DEV_AGENT_DIR', value: ticket.execution?.directory ?? '', description: { zh: '', en: '' }, owner: 'executor' }] })
  const ticket = ticketOf('t1', 'fix-copy-1')
  ticket.execution!.directory = join(root, 'work', 'fix-copy-1')
  store.tickets.save(ticket)
  const created = await worktrees.create(ticket)
  expect(created).toMatchObject({ path: join(root, 'work', 'fix-copy-1'), branch: 'agent/fix-copy-1' })
  expect(existsSync(join(root, 'work', 'fix-copy-1.hook'))).toBe(true)
  expect((await worktrees.list()).find(row => row.branch === 'agent/fix-copy-1')).toMatchObject({ dirty: 0, merged: true, ticket: { id: 't1', open: true } })
  // An open Ticket's worktree is nobody's to remove.
  await expect(worktrees.remove('agent/fix-copy-1')).rejects.toThrow('the open Ticket t1')
  // Nothing to sweep while the Ticket is open.
  const open = await worktrees.sweep()
  expect(open?.removed).toEqual([])
  // Once it ended with its work in the base branch, the sweep removes the worktree, runs the hook and records what it did.
  git('merge', '-q', '--ff-only', 'agent/fix-copy-1')
  store.tickets.save({ ...ticket, ended: { at: new Date().toISOString(), by: 'executor', outcome: 'completed' } })
  const sweep = await worktrees.sweep()
  expect(sweep?.removed).toEqual([{ path: join(root, 'work', 'fix-copy-1'), branch: 'agent/fix-copy-1', ticket: 't1' }])
  expect(existsSync(join(root, 'work', 'fix-copy-1'))).toBe(false)
  expect(existsSync(join(root, 'work', 'fix-copy-1.removed'))).toBe(true)
  expect(store.get(KV.worktrees.sweep)).toEqual(sweep)
  expect((await worktrees.list()).map(row => row.branch)).toEqual(['main'])
  expect(await worktrees.branchOf(ticket)).toBe('agent/fix-copy-1')
  // A dirty worktree stays, and the sweep says why.
  const second = ticketOf('t2', 'fix-copy-2')
  second.execution!.directory = join(root, 'work', 'fix-copy-2')
  store.tickets.save(second)
  await worktrees.create(second)
  writeFileSync(join(root, 'work', 'fix-copy-2', 'note.txt'), 'kept\n')
  git('merge', '-q', '--ff-only', 'agent/fix-copy-2')
  store.tickets.save({ ...second, ended: { at: new Date().toISOString(), by: 'executor', outcome: 'completed' } })
  const kept = await worktrees.sweep()
  expect(kept?.removed).toEqual([])
  expect(kept?.kept).toEqual([expect.objectContaining({ ticket: 't2', reason: '1 uncommitted path' })])
  expect(existsSync(join(root, 'work', 'fix-copy-2'))).toBe(true)
  store.close()
})

it('leaves every directory alone when the deployment has no worktree repository or its cleanup is off', async () => {
  const state = join(root, 'state2')
  mkdirSync(state, { recursive: true })
  const store = new Store(join(state, 'state.sqlite'))
  const worktrees = new TicketWorktrees({ subprocess: realSubprocess as never, store, machine: { stateDir: state }, lifetime: new AbortController().signal,
    environment: () => [] })
  const ticket = ticketOf('t3', 'plain')
  expect(await worktrees.create(ticket)).toBeUndefined()
  expect(await worktrees.sweep()).toBeUndefined()
  expect(await worktrees.list()).toEqual([])
  const executor = store.settings().executor
  store.saveSettings({ ...store.settings(), executor: { ...executor, worktrees: { ...executor.worktrees, repository, cleanup: 'off' } } })
  expect(await worktrees.sweep()).toBeUndefined()
  expect(await worktrees.prune()).toBe(0)
  await expect(worktrees.remove('anything')).rejects.toThrow('No worktree of')
  store.close()
})

it('refuses a path template that leaves the execution root, and a repository that is not one', async () => {
  const state = join(root, 'state3')
  mkdirSync(state, { recursive: true })
  const store = new Store(join(state, 'state.sqlite'))
  const executor = store.settings().executor
  store.saveSettings(SettingsSchema.parse({ ...store.settings(), executor: { ...executor, directory: join(root, 'work'),
    worktrees: { ...executor.worktrees, repository, path: '../{name}' } } }))
  const worktrees = new TicketWorktrees({ subprocess: realSubprocess as never, store, machine: { stateDir: state }, lifetime: new AbortController().signal,
    environment: () => [] })
  await expect(worktrees.create(ticketOf('t4', 'outside'))).rejects.toThrow('leaves the execution root')
  store.saveSettings(SettingsSchema.parse({ ...store.settings(), executor: { ...store.settings().executor,
    worktrees: { ...store.settings().executor.worktrees, repository: join(root, 'not-a-repository'), path: '{name}' } } }))
  await expect(worktrees.create(ticketOf('t5', 'foreign'))).rejects.toThrow('is not a git repository')
  store.close()
})
