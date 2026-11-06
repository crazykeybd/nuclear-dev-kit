# 010 Stage agents

This document describes who does the work: the chief agent that hands it out, and the seven stage agents it hands it to. It
builds on [001 Domain model](001-domain.md) and [003 Execution](003-execution.md).

## The two kinds of agent

The installation runs one main Session and one worker Session per Ticket. The two are now two roles with names a person
reads:

| Agent | 中文 | What it is | What it does |
| --- | --- | --- | --- |
| Chief agent | 总控智能体 | The main Session | Reads requests, decides which stage the work is, accepts a Ticket for that stage agent, and says what the kit accepted. It carries out no stage |
| Stage agent | 阶段智能体 (策划/需求/设计/实现/测试/独立验证/发布) | A worker Session whose Ticket names its stage | Carries out that one stage: its artifact, its Skill, its gate, its report |

The seven stage agents are `plan`, `requirements`, `design`, `implementation`, `test`, `vv` and `release`, in the order the
kit's gate enforces them. Each one owns one stage, one artifact under `.nuclear-dev/`, one Skill of the kit
(`nuclear-plan` … `nuclear-release`) and the gate that judges it. `src/nuclear/agents.ts` holds the table.

## One Ticket, one agent at a time

A Ticket works one stage agent at a time; a chief agent names that agent when it accepts the Ticket. The Ticket records it,
and each Assignment records the agent it works as, so the panel and the reports say who did what.

The stage agent a Ticket works is where its work stands, not where its wording points: the first stage the kit does not
accept is the stage the work is on, and a request about a physical or numerical feature belongs to the stage whose artifact
that feature goes into. A request that spans several stages is accepted once, for the first stage it needs; the Ticket
reaches the later agents in the kit's order.

A Ticket a chief agent names no stage for has no stage agent: it may carry out whichever stage its work is on, as
installations without a kit do. Such a Ticket keeps the behaviour of [003 Execution](003-execution.md).

## The pass to the next agent

A stage agent finishes its stage by the kit's gate, never by its own word:

1. Its worker reports `ready` with what the stage established.
2. The host reads the Ticket's directory from the kit afresh and takes that stage's own verdict.
3. A stage the kit does not accept is returned to the worker with the kit's errors verbatim, and nothing is recorded: the
   agent finishes the artifact and runs the gate again, or reports `blocked` with what the gate said.
4. A stage the kit accepts ends that stage agent's Assignment with the worker's report of it, and the Ticket passes to the
   next stage agent in the kit's order: a new Assignment starts under a `stage` Input that names the agent the worker is now.
5. The last stage, release, passes the Ticket to nobody. The kit accepts it, and the Ticket ends with its work as any Ticket
   ends.

A stage agent that reports `blocked` or `failed`, or asks a question, leaves the Ticket waiting for a person exactly as any
Ticket does. No stage advances while a person's signature is missing: a stage that waits for one is reported as waiting.

The chief agent may hand an open Ticket to a stage agent itself, with `orchestrator_route` kind `stage`: a person's message
that asks for a stage the Ticket has passed, such as a review that asks for a design change, attaches the message and then
dispatches that stage. The gate is never bypassed: the agent runs its stage's gate again before the Ticket moves on.

## One Session per Ticket

Every Assignment of a Ticket runs in the Ticket's one worker Session, and each stage agent is told apart by its part of the
system prompt, its Assignment and its Reports. The prompt section is composed at every model request from the Ticket's
current stage, so an agent that takes over reads its own part from its first step.

This is a deliberate limit: a Ticket's conversation, its background jobs and its worktree stay in one place, and a person
who writes into that Session speaks to whoever works the Ticket now. Giving each stage agent a Session of its own would
split a Ticket's conversation and its worktree bookkeeping across seven Sessions, which the domain does not model.

## What a team may change

The chief agent's part (`runtime/chief`) and each stage agent's part (`runtime/stage/<stage>`) are built-in prompt parts,
so a team may override their text in the panel, and the panel's prompt preview offers each stage agent beside the two roles.
Editing them changes what an agent is told; it does not change the gate, the hand-off rule or the approval rule, which are
code.

## What this does not do

- It does not let an agent sign an approval, pass a stage the kit did not accept, or start a stage the kit has not reached.
- It does not run the seven agents concurrently: the kit's stages are sequential, and a Ticket works one agent at a time.
- It does not give a stage agent a narrower tool set: every stage agent keeps the worker's work tools. A stage that must
  not change source rests on the kit's gate and the review of a person, not on a tool limit.
