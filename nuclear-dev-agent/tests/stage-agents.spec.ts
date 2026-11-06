/**
 * The seven stage agents and the chief agent that hands the work out: the table the panel and the prompts read, the part
 * each agent reads, the ticket a chief agent hands to one agent, and the pass to the next agent once the kit accepts a stage.
 */
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Engine, UserError, latestAssignment, runningAssignment, ticketStage, type Assessor, type Assignment, type Candidate,
  type EngineOptions, type Executor, type Outbox, type Policy, type Ticket, type Trigger } from '../src/core/index.ts'
import { Store } from '../src/app/store.ts'
import { executorTools } from '../src/app/tools/executor.ts'
import type { SourceContext } from '../src/sources/host.ts'
import type { ResourceHost } from '../src/app/resources.ts'
import { CHIEF_AGENT, NUCLEAR_STAGES, STAGE_AGENTS, isNuclearStage, nextStageAgent, stageAgent, stagesFrom } from '../src/nuclear/index.ts'
import { builtInPart, builtInParts, composePrompt, defaultPrompts, promptParts } from '../src/app/prompts.ts'

const member = { source: 'chat', id: 'alice' }
/** A request of its own thread, so a ticket of one request does not decide the next request's message. */
const trigger = (id: string): Trigger => ({ id, source: 'chat', threads: [{ source: 'chat', id: `t${id}` }], actor: member, human: true,
  at: `2026-09-23T00:00:${id.padStart(2, '0')}Z`, text: `message ${id}`,
  channel: { source: 'chat', thread: `t${id}`, address: { message: id } }, meta: {} })

describe('the stage agents', () => {
  it('has one agent per stage, in the kit\'s order, each with its own Skill, artifact and name', () => {
    expect(Object.keys(STAGE_AGENTS)).toEqual([...NUCLEAR_STAGES])
    expect(new Set(NUCLEAR_STAGES.map(stage => STAGE_AGENTS[stage].skill)).size).toBe(NUCLEAR_STAGES.length)
    expect(new Set(NUCLEAR_STAGES.map(stage => STAGE_AGENTS[stage].artifact)).size).toBe(NUCLEAR_STAGES.length)
    for (const stage of NUCLEAR_STAGES) {
      const agent = STAGE_AGENTS[stage]
      expect(agent.stage).toBe(stage)
      expect(agent.skill).toBe(`nuclear-${stage}`)
      expect(agent.artifact.startsWith('.nuclear-dev/') || agent.artifact.startsWith('stages/')).toBe(true)
      expect(agent.name.zh).not.toBe('')
      expect(agent.name.en).not.toBe('')
      expect(agent.mission.zh).not.toBe(agent.mission.en)
    }
    // The chief agent hands the work out; it is not one of the seven.
    expect(CHIEF_AGENT.id).toBe('chief')
    expect(NUCLEAR_STAGES.map(stage => stageAgent(stage)?.name.en)).not.toContain(CHIEF_AGENT.name.en)
  })

  it('passes the ticket on in the kit\'s order, and passes none on after the last stage', () => {
    expect(NUCLEAR_STAGES.map(stage => nextStageAgent(stage)?.stage ?? null)).toEqual([...NUCLEAR_STAGES.slice(1), null])
    expect(nextStageAgent('release')).toBeUndefined()
    expect(stagesFrom('test')).toEqual(['test', 'vv', 'release'])
    expect(isNuclearStage('vv')).toBe(true)
    expect(isNuclearStage('chief')).toBe(false)
    expect(stageAgent(undefined)).toBeUndefined()
  })

  it('gives each stage agent its own prompt part, both roles\' flows, and no other agent\'s part', () => {
    for (const stage of NUCLEAR_STAGES) {
      const part = builtInPart(`runtime/stage/${stage}`)
      expect(part?.roles).toEqual(['worker'])
      expect(part?.text).toContain(`## stage agent · ${stage}`)
      expect(part?.text).toContain(STAGE_AGENTS[stage].name.en)
      expect(promptParts(defaultPrompts(), 'worker', 'env', undefined, stage).map(item => item.name)).toContain(`stage ${stage}`)
      expect(composePrompt(defaultPrompts(), 'worker', 'env', undefined, stage)).toContain(STAGE_AGENTS[stage].skill)
    }
    // The chief agent's part is the main Session's alone, and a team may override either kind of part.
    expect(builtInPart('runtime/chief')?.roles).toEqual(['orchestrator'])
    expect(Object.keys(builtInParts()).filter(key => key.startsWith('runtime/stage/'))).toEqual(NUCLEAR_STAGES.map(stage => `runtime/stage/${stage}`))
    expect(composePrompt(defaultPrompts(), 'orchestrator', 'env', undefined, 'plan')).toContain('## chief agent')
  })
})

const directories: string[] = []
afterEach(() => { for (const dir of directories.splice(0)) rmSync(dir, { recursive: true, force: true }) })

/** An Engine over a real Store, with an Executor that only records what it was asked to run. */
function harness() {
  const dir = mkdtempSync(join(tmpdir(), 'stage-agents-'))
  directories.push(dir)
  const store = new Store(join(dir, 'db'))
  const launches: [Ticket, Assignment][] = []
  const events: { type: string; data: Record<string, unknown> }[] = []
  const requests: Candidate[] = []
  const executor: Executor = { start: vi.fn((ticket, assignment) => { launches.push([ticket, assignment]) }), deliver: vi.fn(), stop: vi.fn() }
  const assessor: Assessor = { request: candidate => { requests.push(candidate) }, release: vi.fn() }
  const policy: Policy = { version: 'v1', paused: false, evalTimeoutMs: 60_000,
    gate: () => ({ admissible: true, strength: 'explicit', basis: { via: 'listed' } }), revalidate: () => true, admitsInferred: () => true }
  const scope: EngineOptions['scope'] = { scope: () => ({ listened: true, observed: false }) }
  const outbox: Outbox = { send: vi.fn(), status: () => 'pending', withdraw: vi.fn() }
  let clock = 0
  const engine = new Engine({ repo: store, scope, policy: () => policy, assessor, executor, outbox,
    prepareTicket: ticket => ({ ...ticket, execution: { name: 'stage-agents', directory: dir, assignment: '' } }),
    emit: event => { events.push({ type: event.type, data: event.data }) },
    now: () => new Date(Date.UTC(2026, 8, 23, 0, 0, clock++)).toISOString() })
  /** Accept the request `id` as a ticket, naming `stage` when the chief agent does. */
  function accept(id: string, stage?: string): Ticket {
    engine.receive(trigger(id))
    engine.evaluateDue()
    const candidate = requests.at(-1)!
    const decision = engine.decide(trigger(id).id, { kind: 'accept', title: 'Write the plan', scope: 'the plan',
      reason: 'requested', acknowledgement: 'ok', ...stage === undefined ? {} : { stage } })
    const ticketId = decision.ticketId
    if (!ticketId) throw new Error(`No ticket: ${JSON.stringify(decision)}`)
    engine.assignmentStarted(ticketId, latestAssignment(store.tickets.get(ticketId)!)!.id)
    return store.tickets.get(ticketId)!
  }
  return { store, engine, launches, events, accept, tick: () => ++clock }
}

describe('a ticket a chief agent hands to a stage agent', () => {
  it('records the stage agent on the ticket and on its first assignment', () => {
    const h = harness()
    const ticket = h.accept('1', 'plan')
    expect(ticket.execution?.stage).toBe('plan')
    expect(latestAssignment(ticket)!.stage).toBe('plan')
    expect(h.launches).toHaveLength(1)
  })

  it('starts a ticket that may carry out the stages itself when the chief names none', () => {
    const ticket = harness().accept('2')
    expect(ticket.execution?.stage).toBeUndefined()
    expect(latestAssignment(ticket)!.stage).toBeUndefined()
  })

  it('refuses a stage the kit does not have, and creates no ticket', () => {
    const h = harness()
    h.engine.receive(trigger('3')); h.engine.evaluateDue()
    expect(() => h.engine.decide('3', { kind: 'accept', title: 'Fix', scope: 'small', reason: 'requested', stage: 'chief' })).toThrow(UserError)
    expect(() => h.engine.decide('3', { kind: 'accept', title: 'Fix', scope: 'small', reason: 'requested', stage: 'chief' }))
      .toThrow('Unknown nuclear stage “chief”')
    expect(h.store.tickets.list()).toHaveLength(0)
    expect(h.launches).toHaveLength(0)
  })
})

describe('the pass to the next stage agent', () => {
  it('ends the accepted stage\'s assignment, starts the next agent\'s, and tells the worker which agent it is now', () => {
    const h = harness()
    const ticket = h.accept('4', 'plan')
    const first = runningAssignment(ticket)!
    const updated = h.engine.stageAccepted(ticket.id, 'plan', 'The planning baseline is written')
    // The accepted stage's own report stays on the Assignment that stage agent worked as.
    const done = updated.assignments.find(item => item.id === first.id)!
    expect(done.state).toBe('ended')
    expect(done.endedReason).toBe('stageAccepted')
    expect(done.report).toMatchObject({ state: 'ready', summary: 'The planning baseline is written' })
    const next = latestAssignment(updated)!
    expect(next.id).not.toBe(first.id)
    expect(next.stage).toBe('requirements')
    expect(updated.execution?.stage).toBe('requirements')
    expect(updated.inputs.at(-1)).toMatchObject({ kind: 'stage', stage: 'requirements', from: 'plan' })
    expect(updated.undelivered).toContain(updated.inputs.at(-1)!.id)
    expect(h.launches.map(([, assignment]) => assignment.stage)).toEqual(['plan', 'requirements'])
    expect(h.events.filter(event => event.type === 'stage.accepted')).toEqual([{ type: 'stage.accepted',
      data: { ticketId: ticket.id, stage: 'plan', next: 'requirements' } }])
    // The ticket is working again, not waiting for review: a new agent has it.
    expect(ticketStage(updated)).toMatchObject({ stage: 'working' })
  })

  it('refuses a stage the ticket does not work, and one no agent follows', () => {
    const h = harness()
    const ticket = h.accept('5', 'design')
    expect(() => h.engine.stageAccepted(ticket.id, 'plan', 'done')).toThrow('The ticket works stage design, not plan')
    expect(latestAssignment(h.store.tickets.get(ticket.id)!)!.state).toBe('running')
    h.engine.stageAccepted(ticket.id, 'design', 'done')
    h.engine.stageAccepted(ticket.id, 'implementation', 'done')
    h.engine.stageAccepted(ticket.id, 'test', 'done')
    h.engine.stageAccepted(ticket.id, 'vv', 'done')
    expect(h.store.tickets.get(ticket.id)!.execution?.stage).toBe('release')
    // Release is the last stage: the ticket ends with its work, and no agent follows it.
    expect(() => h.engine.stageAccepted(ticket.id, 'release', 'done')).toThrow('Stage release is the last one')
  })

  it('lets the chief agent dispatch an open ticket to a stage agent itself, such as one a person sent back', () => {
    const h = harness()
    const ticket = h.accept('6', 'implementation')
    const updated = h.engine.dispatchStage(ticket.id, 'design')
    expect(updated.execution?.stage).toBe('design')
    expect(latestAssignment(updated)!.stage).toBe('design')
    expect(updated.inputs.at(-1)).toMatchObject({ kind: 'stage', stage: 'design' })
    expect(updated.inputs.at(-1)).not.toHaveProperty('from')
    expect(h.events.filter(event => event.type === 'stage.accepted')).toEqual([])
    expect(() => h.engine.dispatchStage(ticket.id, 'chief')).toThrow('Unknown nuclear stage')
    h.engine.stopTicket(ticket.id)
    expect(() => h.engine.dispatchStage(ticket.id, 'design')).toThrow('Ticket has ended')
  })
})

describe('the worker\'s report of its stage', () => {
  /** The executor tools a worker of `ticket` reads, with the kit's verdict stubbed as `verdict`. */
  function tools(h: ReturnType<typeof harness>, ticketId: string, verdict: { passed: boolean; errors: string[] } | undefined) {
    const store = h.store
    const host = { engine: h.engine, store,
      sessions: { relay: vi.fn(), notify: vi.fn() }, resources: {} as ResourceHost,
      github: { deployment: { github: { login: 'agent' } } } as unknown as SourceContext,
      nuclear: { stageVerdict: async () => verdict }, sendReplies: async () => {} }
    return executorTools(host, store.tickets.get(ticketId)!)
  }
  const report = (h: ReturnType<typeof harness>, ticketId: string, verdict?: { passed: boolean; errors: string[] }) =>
    tools(h, ticketId, verdict).find(item => item.name === 'orchestrator_report')!

  it('passes the ticket on only when the kit accepts the stage', async () => {
    const h = harness()
    const ticket = h.accept('7', 'plan')
    const done = await report(h, ticket.id, { passed: true, errors: [] }).execute({ state: 'ready', summary: 'Planning baseline written' }, new AbortController().signal)
    expect(done).toMatchObject({ reported: true, stage: { accepted: 'plan', handed_to: 'requirements' } })
    expect(h.store.tickets.get(ticket.id)!.execution?.stage).toBe('requirements')
  })

  it('refuses the report in the kit\'s own words while the gate blocks the stage', async () => {
    const h = harness()
    const ticket = h.accept('8', 'plan')
    await expect(report(h, ticket.id, { passed: false, errors: ['stages/plan/plan.json: approval missing'] })
      .execute({ state: 'ready', summary: 'done' }, new AbortController().signal))
      .rejects.toThrow('The kit does not accept stage plan: stages/plan/plan.json: approval missing')
    const unchanged = h.store.tickets.get(ticket.id)!
    expect(unchanged.execution?.stage).toBe('plan')
    expect(unchanged.assignments).toHaveLength(1)
    expect(latestAssignment(unchanged)!.report).toBeUndefined()
  })

  it('ends the last stage\'s ticket with its work, and leaves a ticket without a stage agent as it was', async () => {
    const h = harness()
    const ticket = h.accept('9', 'release')
    const done = await report(h, ticket.id, { passed: true, errors: [] }).execute({ state: 'ready', summary: '1.0.0 released' }, new AbortController().signal)
    expect(done).toMatchObject({ reported: true })
    expect(h.store.tickets.get(ticket.id)!.ended?.outcome).toBe('completed')
    // A ticket the chief named no stage for works any stage itself, and its ready report ends it as before.
    const plain = h.accept('10')
    await report(h, plain.id, undefined).execute({ state: 'ready', summary: 'done' }, new AbortController().signal)
    expect(h.store.tickets.get(plain.id)!.ended?.outcome).toBe('completed')
  })
})
