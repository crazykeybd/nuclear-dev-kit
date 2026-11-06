# 009 Worktrees

A Ticket's directory is where its worker does the work, and this document describes the mode in which the Executor makes that
directory a git worktree of a repository, keeps it while the Ticket is open, and gives it back afterwards. It builds on
[003 Execution](003-execution.md), which describes the directory a Ticket's worker starts in and the prepare command.

The mode exists because several Tickets run at once. One checkout cannot hold two branches: two workers would move each other's
files under themselves. A worktree gives each Ticket its own checkout of the same repository, so branches never collide, and a
finished Ticket leaves a branch behind rather than a directory nobody remembers to delete.

## Turning it on

The mode is off until a repository is named. The Execution settings hold it, as `executor.worktrees` in the `executor` block:

| Setting | Default | Meaning |
| --- | --- | --- |
| `repository` | `''` | Absolute path of the repository's checkout on this machine. Empty leaves Ticket directories to the prepare command |
| `path` | `{name}` | A Ticket's directory, relative to the execution root. `{name}` is the Ticket's short name, `{ticket}` its id, `{repo}` the repository's directory name. It must name `{name}` or `{ticket}`, and may not leave the execution root |
| `branch` | `agent/{name}` | The branch of a Ticket's worktree, from the same placeholders |
| `base` | `''` | Where a new branch starts. Empty uses the repository's default branch: `origin/HEAD`, then `origin/main`, `main` or `master` |
| `reuse` | `true` | Check out a branch the repository already has, rather than refusing it |
| `cleanup` | `safe` | Remove the worktree of an ended Ticket once its branch adds nothing to the base branch |
| `deleteBranch` | `true` | Delete that branch with the worktree, when it adds nothing |
| `hooks.create` | `''` | A command `sh` runs once inside the new worktree |
| `hooks.remove` | `''` | A command `sh` runs inside the worktree before it is removed |

Only the panel changes these, like the rest of the execution environment. A save takes effect on the next Ticket or the next
sweep, without a restart.

## What a launch does

A launch prepares a Ticket's directory only when it does not exist, as [003 Execution](003-execution.md) describes. With a
repository set, that preparation creates a worktree instead of leaving the work to the prepare command:

1. The path and branch are rendered from their templates, and the path must stay inside the execution root.
2. The repository must be a git repository with at least one commit.
3. A record of a worktree whose directory someone deleted is dropped first, so the path can be used again.
4. `git worktree add` checks out the branch: one the repository already has is checked out again when `reuse` holds, and a new one
   starts at `base`. Checking an existing branch out again is what lets a resumed Ticket find the work of its earlier Assignment.
5. The create hook runs inside the worktree, with the execution environment's variables, for up to ten minutes.

The prepare command then still runs, in the execution root, with the Ticket's environment. It can no longer be what creates the
directory, so it is the place for a `git fetch`, an install or an env file. A failure at any step fails the Ticket with the
output and leaves the Ticket waiting for a person, as a failed prepare command does.

The branch a Ticket's worker pushes is `agent/<short name>`, whose last path segment is the Ticket's short name, so a pull
request opened from it belongs to the Ticket.

## What a sweep does

Once a minute count passes, the Executor sweeps: shortly after startup, then every fifteen minutes. `orchestrator_worktrees`
with `operation: sweep` runs the same sweep when a person asks.

The sweep reads the repository's worktrees and considers only those inside the execution root that an ended Ticket's directory
names. For each, the worktree stays when any of these holds, and the sweep records the reason:

- the worktree is detached, since its commits need not reach any branch;
- its state cannot be read;
- it holds uncommitted paths, including untracked files;
- its branch still adds something to the base branch.

Otherwise the remove hook runs in the worktree, and `git worktree remove` takes it away. The branch is deleted only when it adds
nothing to the base branch, and `deleteBranch` holds; a branch git itself refuses to delete stays, and the sweep records that too.

"A branch adds nothing to the base branch" is answered by the first check that says yes: the same commit, an ancestor of the base,
an empty three-dot diff, equal trees, a merge that produces the base's tree, or commits whose patch the base already has — which is
what a squash merge leaves. A branch that adds work is never deleted, so its commits stay reachable from the branch alone.

The sweep then prunes the records of worktrees whose directories are gone, and stores what it did, with the time, the removed
worktrees, the ones it kept and why. `orchestrator_worktrees` with `operation: list` reads that record along with the worktrees as they
stand now: their branch, their uncommitted paths, how far they are from the base branch, whether they are safe to remove, and the
Ticket that works in one.

## What is never removed

- A worktree of an open Ticket: its worker may still write there, so `orchestrator_worktrees` with `operation: remove` refuses it.
  Ending the Ticket, or stopping it, is what makes the worktree eligible.
- A worktree with uncommitted paths, unless the removal names `force`. An ended Ticket's sweep never forces anything.
- A branch that still adds work to the base, unless the removal names `force`.
- A worktree that no ended Ticket names: another tool's checkout, or a person's, under the same root stays untouched.

Removing a worktree discards its checkout, never the branch that holds its committed work. Removing it while a worker's shell job
still runs there is what the open-Ticket refusal prevents.

## Failure and recovery

A failed create fails the Ticket and records the output, and a retry or a person's message tries again; the directory is removed
first, so a half-made checkout is not mistaken for a prepared one. A failed remove hook keeps the worktree and records the reason,
so nothing is lost to a hook that could not finish.

A Ticket that ended, and whose worktree the sweep removed, can still be resumed: its directory is missing, so the next launch
creates the worktree again — on the branch when it is still there, and from `base` when the merge let the sweep delete it.

## Related

- The execution root, the prepare command and the execution environment: [003 Execution](003-execution.md).
- The panel's Execution settings, where these fields live: [005 Panel](005-panel.md).
- The deployment steps that name a clone to work from: [006 Deployment](006-deployment.md).
