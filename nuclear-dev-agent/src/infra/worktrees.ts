/**
 * Git worktrees of the repository a deployment works in: the operations of `git worktree` a Ticket needs, and the checks that
 * keep a removal from discarding work.
 * Commands run through the caller's git, so a worktree sees the agent's configuration and credentials, never the operator's.
 * The questions "may this branch be deleted" and "may this worktree go" are answered here once, for the Executor that cleans up
 * after a Ticket and for the tool a person uses to look at the worktrees.
 */
import { basename, isAbsolute, relative, resolve, sep } from 'node:path'
import type { SubprocessOutputReader, SubprocessRuntime } from '@deepseek-ai/dsh-subprocess'
import { GIT_LOCATION } from './environment.ts'

/** The outcome of one git command: its exit status and both streams, which a check reads rather than an exception. */
export interface GitOutput { code: number; stdout: string; stderr: string }
/** Runs one git command in `cwd`; a command that cannot start at all rejects. */
export type GitRun = (argv: readonly string[], cwd: string, signal?: AbortSignal) => Promise<GitOutput>

/** Runs git for the agent: the DSH subprocess runtime, with the credential-shaped variables stripped and output capped. */
export function gitRun(subprocess: SubprocessRuntime): GitRun {
  return async (argv, cwd, signal) => {
    const handle = subprocess.spawn({ argv: ['git', ...argv], cwd, graceMs: 2000, ...signal ? { signal } : {},
      stdio: { stdin: 'ignore', stdout: { maxBytes: 1 << 20 }, stderr: { maxBytes: 1 << 16 } } })
    const { exitCode } = await handle.done
    const read = (reader: SubprocessOutputReader | undefined): string => reader?.readFrom(0).text ?? ''
    return { code: exitCode ?? 1, stdout: read(handle.collected.stdout), stderr: read(handle.collected.stderr) }
  }
}
/** One worktree as `git worktree list --porcelain` reports it. */
export interface WorktreeEntry {
  /** Absolute path of the worktree. */
  path: string
  /** Commit the worktree has checked out. */
  head?: string
  /** The local branch it is on; absent when it is detached. */
  branch?: string
  bare: boolean
  detached: boolean
  /** Why git would prune it, such as a directory that is gone. */
  prunable?: string
}
/** What a worktree holds beyond its branch: how many paths are uncommitted, and how its branch stands to the base. */
export interface WorktreeState { dirty: number; ahead: number; behind: number }
/** What a removal did, and what it left: `kept` names the reason the worktree or the branch stayed. */
export interface RemovalResult {
  path: string
  removed: boolean
  kept?: 'uncommitted changes' | 'directory is not a worktree'
  branch?: string
  branchDeleted?: boolean
  branchKept?: 'unmerged changes' | 'checked out elsewhere'
}
/** The values a Ticket's path and branch templates render from. */
export interface WorktreeNames { name: string; ticket: string; repo: string }

/** Renders a path or branch template: `{name}`, `{ticket}` and `{repo}` are replaced, and every other character is literal. */
export function renderWorktree(template: string, values: WorktreeNames): string {
  return template.replace(/\{(name|ticket|repo)\}/g, (_match, key: keyof WorktreeNames) => values[key])
}
/**
 * The directory a template names below `root`, or undefined when it leaves the root.
 * An absolute template stands on its own; a relative one is read from the execution root, which keeps Ticket directories together.
 */
export function worktreePath(root: string, template: string, values: WorktreeNames): string | undefined {
  const rendered = renderWorktree(template, values)
  const path = isAbsolute(rendered) ? resolve(rendered) : resolve(root, rendered)
  const inside = relative(resolve(root), path)
  return inside === '' || inside.startsWith('..') || isAbsolute(inside) ? undefined : path
}
/** True when `path` is `root` or lies below it, which is where a sweep may remove a directory. */
export function within(root: string, path: string): boolean {
  const inside = relative(resolve(root), resolve(path))
  return inside === '' || !inside.startsWith('..') && !isAbsolute(inside) && !inside.startsWith(`..${sep}`)
}

/**
 * The worktrees of one repository.
 * Reads are tolerant: a worktree whose directory is gone still lists, with what git knows of it.
 */
export class Worktrees {
  constructor(readonly git: GitRun, readonly repository: string) {}
  /** Runs one command and returns its output, or throws the git error text when the exit status is not 0. */
  private async text(argv: readonly string[], cwd = this.repository, signal?: AbortSignal): Promise<string> {
    const { code, stdout, stderr } = await this.git(argv, cwd, signal)
    if (code !== 0) throw new Error(stderr.trim() || `git ${argv.join(' ')} exited with ${code}`)
    return stdout
  }
  /** Runs one command whose exit status answers a yes-or-no question: 0 is yes, 1 is no, anything else is an error. */
  private async answers(argv: readonly string[], cwd = this.repository, signal?: AbortSignal): Promise<boolean> {
    const { code, stderr } = await this.git(argv, cwd, signal)
    if (code === 0) return true
    if (code === 1) return false
    throw new Error(stderr.trim() || `git ${argv.join(' ')} exited with ${code}`)
  }
  /** Every worktree of the repository, the main one first, in the order `git worktree list` reports them. */
  async list(signal?: AbortSignal): Promise<WorktreeEntry[]> {
    return parseWorktrees(await this.text(['worktree', 'list', '--porcelain'], this.repository, signal))
  }
  /** True when the directory is a git repository with at least one commit, which an empty or foreign directory is not. */
  async usable(signal?: AbortSignal): Promise<boolean> {
    try {
      return await this.answers(['rev-parse', '--git-dir'], this.repository, signal)
        && await this.answers(['rev-parse', '--verify', '--quiet', 'HEAD^{commit}'], this.repository, signal)
    } catch { return false }
  }
  /** The branch new work starts from: the one set, else the remote's default branch, else the checked-out branch, else `main`. */
  async defaultBranch(signal?: AbortSignal): Promise<string> {
    const remote = (await this.git(['symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD'], this.repository, signal)).stdout.trim()
    if (remote) return remote
    for (const name of ['origin/main', 'origin/master', 'main', 'master']) {
      if (await this.answers(['rev-parse', '--verify', '--quiet', `${name}^{commit}`], this.repository, signal)) return name
    }
    const current = (await this.git(['symbolic-ref', '--quiet', '--short', 'HEAD'], this.repository, signal)).stdout.trim()
    return current || 'HEAD'
  }
  /** The local branch of that name, or undefined when the repository has none. */
  async branch(name: string, signal?: AbortSignal): Promise<string | undefined> {
    return await this.answers(['rev-parse', '--verify', '--quiet', `refs/heads/${name}^{commit}`], this.repository, signal) ? name : undefined
  }
  /**
   * Creates the worktree at `path`, on `branch`: a branch the repository already has is checked out again, so a Ticket that
   * resumes finds the work of its earlier Assignment, and a new one starts at `base`.
   * @throws When another worktree already holds the branch, or git refuses the path.
   */
  async create(input: { path: string; branch: string; base?: string; reuse?: boolean }, signal?: AbortSignal): Promise<{ path: string; branch: string; reused: boolean }> {
    const { path, branch, base } = input
    const existing = await this.branch(branch, signal)
    if (existing && input.reuse !== false) {
      const holder = (await this.list(signal)).find(entry => entry.branch === branch)
      // A branch has one worktree: another one's directory is not this Ticket's, and switching it there would take that work away.
      if (holder && resolve(holder.path) !== resolve(path)) throw new Error(`The branch ${branch} is checked out at ${holder.path}`)
      if (!holder) {
        await this.text(['worktree', 'add', path, branch], this.repository, signal)
        return { path, branch, reused: true }
      }
    }
    else if (existing) throw new Error(`The branch ${branch} exists; set reuse to check it out again`)
    await this.text(['worktree', 'add', '-b', branch, path, ...base ? [base] : []], this.repository, signal)
    return { path, branch, reused: false }
  }
  /** How a worktree stands: its uncommitted paths, and how far its branch is from `base`. */
  async state(entry: { path: string; branch?: string }, base?: string, signal?: AbortSignal): Promise<WorktreeState> {
    const dirty = (await this.git(['status', '--porcelain', '--untracked-files=normal'], entry.path, signal)).stdout
    const paths = dirty.split('\n').filter(line => line.trim() !== '').length
    if (!entry.branch || !base) return { dirty: paths, ahead: 0, behind: 0 }
    // `--left-right` counts the base's own commits first and the branch's second, so the branch is ahead by the second.
    const counts = (await this.git(['rev-list', '--left-right', '--count', `${base}...${entry.branch}`], this.repository, signal)).stdout.trim().split(/\s+/)
    return { dirty: paths, ahead: Number(counts[1] ?? 0), behind: Number(counts[0] ?? 0) }
  }
  /**
   * Whether merging `branch` into `base` would add nothing, which is what makes a worktree safe to remove and its branch to delete.
   * The checks run cheapest first: an equal commit, an ancestor, an empty three-dot diff, equal trees, a merge that adds nothing,
   * and a branch whose commits all reach `base` by patch id, which covers a squash merge. The first yes answers.
   */
  async addsNothing(branch: string, base: string, signal?: AbortSignal): Promise<boolean> {
    const commit = async (ref: string): Promise<string> => (await this.text(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`], this.repository, signal)).trim()
    const tip = await commit(branch).catch(() => '')
    const onto = await commit(base).catch(() => '')
    // A branch git cannot resolve, or a base it cannot compare with, is not one to delete.
    if (!tip || !onto) return false
    if (tip === onto) return true
    if (await this.answers(['merge-base', '--is-ancestor', tip, onto], this.repository, signal)) return true
    if (await this.answers(['diff', '--quiet', `${onto}...${tip}`, '--'], this.repository, signal)) return true
    const [branchTree, baseTree] = await Promise.all([commit(`${tip}^{tree}`).catch(() => ''), commit(`${onto}^{tree}`).catch(() => '')])
    if (branchTree && branchTree === baseTree) return true
    const merged = await this.git(['merge-tree', '--write-tree', onto, tip], this.repository, signal)
    if (merged.code === 0 && merged.stdout.trim().split('\n')[0] === baseTree) return true
    // `git cherry` marks with `+` the commits whose patch the base does not have; without one, nothing is missing.
    const cherry = await this.git(['cherry', onto, tip], this.repository, signal)
    return cherry.code === 0 && !cherry.stdout.split('\n').some(line => line.startsWith('+'))
  }
  /**
   * Removes the worktree at `path`, and the branch with it when the branch would add nothing to `base`.
   * A worktree with uncommitted paths is kept unless `force`, and so is an unmerged branch unless `force`.
   */
  async remove(input: { path: string; branch?: string; base?: string; force?: boolean; deleteBranch?: boolean }, signal?: AbortSignal): Promise<RemovalResult> {
    const { path, branch, base, force = false, deleteBranch = true } = input
    const entry = (await this.list(signal)).find(candidate => resolve(candidate.path) === resolve(path))
    if (!entry) return { path, removed: false, kept: 'directory is not a worktree' }
    const state = await this.state(entry, base, signal)
    if (state.dirty > 0 && !force) return { path, removed: false, kept: 'uncommitted changes', ...branch ? { branch } : {} }
    const removed = await this.git(['worktree', 'remove', ...force ? ['--force'] : [], entry.path], this.repository, signal)
    if (removed.code !== 0) throw new Error(removed.stderr.trim() || `git worktree remove exited with ${removed.code}`)
    const name = branch ?? entry.branch
    if (!name || !deleteBranch) return { path, removed: true, ...name ? { branch: name } : {} }
    if (!force && !await this.addsNothing(name, base ?? await this.defaultBranch(signal), signal)) return { path, removed: true, branch: name, branchDeleted: false, branchKept: 'unmerged changes' }
    if ((await this.list(signal)).some(other => other.branch === name)) return { path, removed: true, branch: name, branchDeleted: false, branchKept: 'checked out elsewhere' }
    const deleted = await this.git(['branch', force ? '-D' : '-d', name], this.repository, signal)
    // A branch git refuses to delete, such as an empty commit that no merge carried, stays and is reported rather than failing the removal.
    if (deleted.code !== 0) return { path, removed: true, branch: name, branchDeleted: false, branchKept: 'unmerged changes' }
    return { path, removed: true, branch: name, branchDeleted: true }
  }
  /** Drops the records of worktrees whose directories are gone, and reports how many. */
  async prune(signal?: AbortSignal): Promise<number> {
    const before = (await this.list(signal)).length
    await this.text(['worktree', 'prune'], this.repository, signal)
    return Math.max(before - (await this.list(signal)).length, 0)
  }
}

/** Parses `git worktree list --porcelain`: one block per worktree, its fields one per line, blocks separated by a blank line. */
export function parseWorktrees(text: string): WorktreeEntry[] {
  const entries: WorktreeEntry[] = []
  for (const block of text.split(/\n\s*\n/)) {
    const lines = block.split('\n').filter(line => line.trim() !== '')
    if (!lines.length) continue
    const entry: WorktreeEntry = { path: '', bare: false, detached: false }
    for (const line of lines) {
      const [field, ...rest] = line.split(' ')
      const value = rest.join(' ')
      if (field === 'worktree' && value) entry.path = value
      else if (field === 'HEAD') entry.head = value
      else if (field === 'branch') entry.branch = value.replace(/^refs\/heads\//, '')
      else if (field === 'bare') entry.bare = true
      else if (field === 'detached') entry.detached = true
      else if (field === 'prunable') entry.prunable = value || 'git would prune it'
    }
    if (entry.path) entries.push(entry)
  }
  return entries
}

/** The directory a repository is checked out in, by the name a `{repo}` template needs: the last part of its path. */
export const repositoryName = (repository: string): string => basename(resolve(repository))

/** A Ticket's directory and branch in a repository, both rendered from templates. */
export function ticketWorktree(names: WorktreeNames, config: { path: string; branch: string }, root: string): { directory: string | undefined; branch: string } {
  return { directory: worktreePath(root, config.path || '{name}', names), branch: renderWorktree(config.branch, names) }
}
