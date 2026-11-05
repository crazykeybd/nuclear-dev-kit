// @vitest-environment jsdom
// The Nuclear tab and the stage section of a Ticket page.
import { expect, it } from 'vitest'
import type { TicketPageView } from '../src/client/api.ts'
import { zh } from '../src/client/locales.ts'
import { usePanel, mount, all, click, tab, text } from './fixtures/panel.tsx'
import { nuclearBoard, nuclearProject, nuclearStage, server } from './fixtures/panel-server.ts'

usePanel()

it('says which kit it runs, and that the flow is off when the deployment names none', async () => {
  await mount()
  await click(zh['tab.nuclear'])
  expect(tab(zh['tab.nuclear']).getAttribute('aria-selected')).toBe('true')
  expect(document.querySelector('.dt-status-title')?.textContent).toBe(zh.statusTitle)
  // An installation without a kit shows what to set instead of an empty board, and its problem as the kit reports it.
  expect(text()).toContain(zh.nuclearOff)
  expect(text()).toContain('No nuclear-dev-kit is configured for this installation.')
  expect(all('.dt-section-title')).toEqual([])
  expect(server.requests.some(request => request.path === 'nuclear')).toBe(true)
})

it('shows each workspace\'s seven stages with the kit\'s own messages, the stage a signature holds, and a fresh check', async () => {
  server.nuclear = nuclearBoard()
  await mount()
  await click(zh['tab.nuclear'])
  expect(text()).toContain(zh.nuclearKitReady)
  expect(text()).toContain('/srv/nuclear-dev-kit')
  expect(text()).toContain('Python 3.12.3')
  // The board counts the stages by state, then lists them in the kit's order.
  const counts = all('.dt-status-line .dt-lv').map(item => item.textContent)
  expect(counts.slice(2, 8)).toEqual([`${zh.nuclearCountProjects} 1`, `${zh['nuclearState.passed']} 2`,
    `${zh['nuclearState.awaiting-approval']} 1`, `${zh['nuclearState.blocked']} 0`, `${zh['nuclearState.missing']} 4`,
    `${zh.nuclearCountComplete} 0`])
  const section = document.querySelector('.dt-section')!
  expect(section.querySelector('.dt-section-name')?.textContent).toBe('示范求解器')
  expect([...section.querySelectorAll('.dt-row-title')].map(title => title.firstElementChild?.textContent)).toEqual([
    zh['stage.plan'], zh['stage.requirements'], zh['stage.design'], zh['stage.implementation'], zh['stage.test'], zh['stage.vv'],
    zh['stage.release']])
  // A stage's state is its own words, and the kit's message is quoted as written.
  expect([...section.querySelectorAll('.dt-tag')].map(tag => tag.textContent)).toEqual([zh['nuclearState.passed'],
    zh['nuclearState.passed'], zh['nuclearState.awaiting-approval'], zh['nuclearState.missing'], zh['nuclearState.missing'],
    zh['nuclearState.missing'], zh['nuclearState.missing']])
  expect(section.textContent).toContain('approval.scope: 必须包含当前阶段产物 stages/design/design.json')
  // The gate of the stage the work stands on names its count.
  expect(text()).toContain('设计 的递归门禁未通过')
  await click(zh.nuclearRefresh)
  expect(server.requests.some(request => request.path === 'nuclear/refresh' && request.method === 'POST')).toBe(true)
})

it('lists a Ticket\'s stages on its page, with the kit\'s messages and a link to the whole board', async () => {
  const project = nuclearProject()
  // The host adds `nuclear` to a Ticket page once its directory holds a kit workspace.
  const detail = server.ticketDetails.t1 as TicketPageView
  server.ticketDetails.t1 = { ...detail, nuclear: { checkedAt: project.checkedAt, stages: project.stages,
    project: project.project, next: project.next, gate: project.gate, passed: project.passed, complete: project.complete,
    attention: project.attention } } as TicketPageView
  await mount()
  await click(all('.dt-open').find(button => button.textContent === '修复回归')!)
  expect(all('.dt-section-title').map(title => title.querySelector('.dt-section-name')?.textContent)).toContain(zh.nuclearStagesTitle)
  expect(text()).toContain(zh['stage.design'])
  expect(text()).toContain('approval.scope: 必须包含当前阶段产物 stages/design/design.json')
  await click(zh.nuclearOpenBoard)
  expect(tab(zh['tab.nuclear']).getAttribute('aria-selected')).toBe('true')
})

it('leads the overview with the stages the gate stops on', async () => {
  const project = nuclearProject()
  server.nuclear = nuclearBoard()
  // The overview reads its own route, which the fake answers from the same workspaces.
  await mount()
  expect(all('.dt-section-title').map(title => title.querySelector('.dt-section-name')?.textContent)).toContain(
    zh.nuclearAttentionTitle)
  expect(text()).toContain('等待人工批准')
  expect(text()).toContain(project.root)
  await click(zh.details)
  expect(tab(zh['tab.nuclear']).getAttribute('aria-selected')).toBe('true')
})
