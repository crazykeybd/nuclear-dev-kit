/** Execution status view (active Tickets and pause control) and Execution settings group (Executor capacity and workspace environment). */
import { useRef, useState } from 'react'
import { TICKET_FILTERS, type TicketFilter } from '../app/api.ts'
import { LIMITS } from '../limits.ts'
import { usePoll, type SettingsView, type SourceView, type StateView } from './api.ts'
import { Button, DisclosureRow, Icon, InfoTip, Input, Pill, SegmentedControl, Switch } from './controls.tsx'
import { SaveBar } from './draft.tsx'
import { usePanel } from './provider.tsx'
import { TicketLine } from './rows.tsx'
import { ConfigHistory, Field, Fields, ModelField, numberOf, useBlockDraft, useSettings } from './settings-kit.tsx'
import { localized, when } from './text.ts'
import { ConfirmButton, Hint, LabelValue, LoadMore, LoadState, Section, StatusHead } from './widgets.tsx'

/**
 * The Ticket worktrees of the deployment, as `wt list` shows them: the branch, the Ticket that works in each, what stands in the way
 * of a removal, and the sweep that cleans up after ended Tickets. A worktree of an open Ticket offers no removal.
 */
function Worktrees({ reload }: { reload: () => Promise<void> }) {
  const { t, call } = usePanel()
  const { data, error, reload: reloadWorktrees } = usePoll(() => call('GET worktrees'), [], 15_000)
  const sweep = async () => { await call('POST worktrees/sweep'); await reloadWorktrees() }
  const remove = async (target: string) => { await call('POST worktrees/remove', { body: { target } }); await reloadWorktrees(); await reload() }
  const stateOf = (row: NonNullable<typeof data>['worktrees'][number]): string => [row.dirty > 0 ? t('worktreeDirty', { count: String(row.dirty) }) : '',
    row.ahead > 0 ? t('worktreeAhead', { count: String(row.ahead) }) : '', row.behind > 0 ? t('worktreeBehind', { count: String(row.behind) }) : '',
    row.merged ? t('worktreeMerged') : '', row.detached ? t('worktreeDetached') : ''].filter(Boolean).join(' · ') || t('worktreeClean')
  return <Section title={t('worktreesTitle')} count={data?.worktrees.length} hint={t('worktreesListHint')}
    action={data?.repository ? <ConfirmButton variant="outline" icon="refresh" label={t('worktreeSweepNow')}
      title={t('worktreeSweepNow')} message={t('worktreeSweepConfirm')} onConfirm={sweep} /> : undefined}>
    <LoadState error={error} loading={!data} />
    {data && !data.repository && <Hint>{t('worktreeListUnset')}</Hint>}
    {data?.repository && (data.worktrees.length ? <table className="dt-table">
      <thead><tr><th>{t('worktreeBranch')}</th><th>{t('worktreeTicket')}</th><th>{t('worktreeState')}</th><th /></tr></thead>
      <tbody>{data.worktrees.map(row => <tr key={row.path}>
        <td className="dt-mono" title={row.path}>{row.branch ?? row.path}</td>
        <td>{row.ticket ? row.ticket.title : <span className="dt-hint">{t('worktreeNoTicket')}</span>}</td>
        <td>{stateOf(row)}</td>
        <td>{!row.ticket?.open && <Button size="sm" variant="ghost" onClick={() => { void remove(row.branch ?? row.path) }}>{t('worktreeRemove')}</Button>}</td>
      </tr>)}</tbody>
    </table> : <Hint>{t('worktreesNone')}</Hint>)}
    {data?.lastSweep && <Hint>{t('worktreeLastSweep', { at: when(data.lastSweep.at, t('lang')), removed: String(data.lastSweep.removed.length),
      kept: String(data.lastSweep.kept.length) })}</Hint>}
  </Section>
}
export function ExecutionStatus({ filter: current, state, reload }: {
  filter: TicketFilter; state: StateView; reload: () => Promise<void>
}) {
  const { t, call, navigate } = usePanel()
  const [limit, setLimit] = useState(20)
  const { data, error, reload: reloadTickets } = usePoll(() => call('GET tickets', { query: { state: current, limit } }), [current, limit])
  const { paused, load: { maxWorkers } } = state
  // Pausing uses its own block revision so toggling pause does not invalidate an open Execution settings draft.
  const pause = async () => { await call('POST executor/pause', { body: { paused: !paused } }); await reload() }
  const status = state.setup.problem ? { tone: 'warning', label: t('executorWaitingSetup') } : paused ? { tone: 'warning',
    label: t('processingPaused') }
    : { tone: 'ongoing', label: t('executorRunning') }
  const action = paused ? 'resumeProcessing' : 'pauseProcessing'
  return <>
    <StatusHead hint={t('executionStatusIntro')} settings="execution" />
    <div className="dt-row-meta dt-status-line">
      <span className="dt-status-text" data-state={status.tone}>{status.label}</span>
      {!state.setup.problem && <>
        <LabelValue label={t('executingLabel')}
          value={`${state.load.running} / ${maxWorkers}`} /><LabelValue label={t('queuedLabel')} value={state.load.queued} />
      </>}
      <ConfirmButton variant="outline" icon={paused ? 'play' : 'pause'} label={t(action)} title={t(action)} message={t(paused
        ? 'resumeProcessingConfirm' : 'pauseProcessingConfirm')}
        onConfirm={pause} />
    </div>
    <div className="dt-filters">
      {TICKET_FILTERS.map(value => <Pill key={value} active={current === value}
        onClick={() => { setLimit(20); navigate({ page: 'execution', query: value === 'open' ? {} : { filter: value } },
          true) }}>{t(`ticketFilter.${value}`)}</Pill>)}
    </div>
    {current === 'idle' && <Hint>{t('idleHint')}</Hint>}
    <Worktrees reload={reload} />
    <LoadState error={error} loading={!data} />
    {data && (data.items.length ? <ul className="dt-list">{data.items.map(ticket => ticket.stage === 'person'
      ? <TicketLine key={ticket.id} ticket={ticket} question
        onChanged={reloadTickets} /> : <TicketLine key={ticket.id} ticket={ticket} />)}</ul> : <Hint>{t('none')}</Hint>)}
    {data?.next_offset != null && <LoadMore onMore={() => setLimit(limit + 20)} />}
  </>
}

const firstSentence = (text: string): string => /^[^。；;.]*(?:[。；;]|\.(?=\s|$))?/.exec(text)?.[0] ?? text
function EnvironmentVariables({ groups, sources,
  onPick }: { groups: SettingsView['environment']['variables']; sources: SourceView[]; onPick: (key: string) => void }) {
  const { t } = usePanel()
  const [open, setOpen] = useState(false)
  const owner = (id: string) => id === 'executor' ? t('term.executor') : localized(t, sources.find(source => source.id === id)?.title ?? id)
  const count = groups.reduce((sum, group) => sum + group.variables.length, 0)
  return <DisclosureRow icon={<Icon name="hash" />} title={<>{t('environmentVariables')} <span className="dt-count">{count}</span></>}
    open={open} onToggle={() => setOpen(!open)}>
    <div className="dt-disclosure-body">
      <Hint>{t('environmentPick')}</Hint>
      <table className="dt-table">
        <thead><tr><th>{t('environmentKey')}</th><th>{t('environmentDescription')}</th><th>{t('environmentOwner')}</th></tr></thead>
        <tbody>{groups.flatMap(group => group.variables.map(variable => <tr key={variable.key}>
          <td><button type="button" className="dt-textlink dt-mono" onClick={() => onPick(variable.key)}>{variable.key}</button></td>
          <td title={localized(t, variable.description)}>{firstSentence(localized(t, variable.description))}</td>
          <td>{owner(group.owner)}{!group.enabled && <span className="dt-hint"> · {t('sourceOff')}</span>}</td>
        </tr>))}</tbody>
      </table>
    </div>
  </DisclosureRow>
}
/** One worktree setting that is switched on or off, with the hint that says what switching it changes. */
function SwitchField({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (next: boolean) => void }) {
  return <div className="dt-switch-row">
    <div className="dt-field-head">{label}<InfoTip text={hint} /></div>
    <Switch checked={checked} onChange={onChange} label={label} />
  </div>
}
export function ExecutionSettings() {
  const { t } = usePanel()
  const { blocks, environment, sources } = useSettings().settings
  // Keep raw user text (such as separators between blocked commands) in the draft and parse only on save.
  const executor = blocks.executor.value
  const saved = { ...executor, maxWorkers: String(executor.maxWorkers), blockedCommands: executor.blockedCommands.join(' ') }
  const draft = useBlockDraft('executor', saved, blocks.executor.revision,
    value => ({ ...value, maxWorkers: numberOf(value.maxWorkers), blockedCommands: value.blockedCommands.split(/[\s,]+/).filter(Boolean) }))
  const value = draft.value
  const edit = (next: Partial<typeof value>) => draft.edit({ ...value, ...next })
  const prepare = useRef<HTMLTextAreaElement>(null)
  const insert = (key: string) => {
    const field = prepare.current
    const at = field?.selectionStart ?? value.prepare.length, to = field?.selectionEnd ?? at
    edit({ prepare: `${value.prepare.slice(0, at)}"$${key}"${value.prepare.slice(to)}` })
    requestAnimationFrame(() => { field?.focus(); const caret = at + key.length + 3; field?.setSelectionRange(caret, caret) })
  }
  return <div className="dt-form">
    <form className="dt-form" onSubmit={event => { void draft.submit(event) }}>
      <Fields disabled={draft.busy}>
        <div className="dt-form dt-block">
          <h2 className="dt-block-title">{t('term.executor')}<InfoTip text={t('executorIntro')} /></h2>
          <Section title={t('executorModel')} hint={t('executorModelHint')}><ModelField id="dt-worker-model" value={value.model}
            onChange={model => edit({ model })} /></Section>
          <Field label={t('maxWorkers')} hint={t('maxWorkersHint')}>
            <Input type="number" min={LIMITS.maxWorkers.min} max={LIMITS.maxWorkers.max} required value={value.maxWorkers}
              onChange={event => edit({ maxWorkers: event.target.value })} />
          </Field>
        </div>
        <div className="dt-form dt-block">
          <h2 className="dt-block-title">{t('term.environment')}<InfoTip text={t('environmentIntro')} /></h2>
          <Field label={t('executionDirectory')} hint={t('executionDirectoryHint')} note={value.directory ? undefined
            : t('executionDirectoryDefault', { root: environment.root })}>
            <Input className="dt-mono" value={value.directory} placeholder={t('executionDirectoryEmpty')} spellCheck={false} pattern="/.*"
              onChange={event => edit({ directory: event.target.value })} />
          </Field>
          <Field label={t('prepareCommand')} hint={t('prepareCommandHint')}>
            <textarea ref={prepare} className="dt-textarea dt-mono" rows={3} maxLength={LIMITS.prepareCommand} spellCheck={false}
              placeholder={t('prepareCommandEmpty')} value={value.prepare}
              onChange={event => edit({ prepare: event.target.value })} />
          </Field>
          <EnvironmentVariables groups={environment.variables} sources={sources} onPick={insert} />
          <div className="dt-form">
            <Section title={t('worktreesTitle')} hint={t('worktreesHint')}>
              <Field label={t('worktreeRepository')} hint={t('worktreeRepositoryHint')} note={value.worktrees.repository ? undefined
                : t('worktreeRepositoryEmpty')}>
                <Input className="dt-mono" value={value.worktrees.repository} placeholder={t('worktreeRepositoryEmpty')}
                  spellCheck={false} pattern="/.*" onChange={event => edit({ worktrees: { ...value.worktrees, repository: event.target.value } })} />
              </Field>
              <div className="dt-grid3">
                <Field label={t('worktreePath')} hint={t('worktreePathHint')}>
                  <Input className="dt-mono" value={value.worktrees.path} placeholder="{name}" spellCheck={false}
                    onChange={event => edit({ worktrees: { ...value.worktrees, path: event.target.value } })} />
                </Field>
                <Field label={t('worktreeBranch')} hint={t('worktreeBranchHint')}>
                  <Input className="dt-mono" value={value.worktrees.branch} placeholder="agent/{name}" spellCheck={false}
                    onChange={event => edit({ worktrees: { ...value.worktrees, branch: event.target.value } })} />
                </Field>
                <Field label={t('worktreeBase')} hint={t('worktreeBaseHint')}>
                  <Input className="dt-mono" value={value.worktrees.base} placeholder={t('worktreeBaseEmpty')} spellCheck={false}
                    onChange={event => edit({ worktrees: { ...value.worktrees, base: event.target.value } })} />
                </Field>
              </div>
              <Section title={t('worktreeCleanup')} hint={t('worktreeCleanupHint')}>
                <SegmentedControl label={t('worktreeCleanup')} value={value.worktrees.cleanup}
                  options={[{ value: 'off', label: t('worktreeCleanupOff') }, { value: 'safe', label: t('worktreeCleanupSafe') }]}
                  onChange={cleanup => edit({ worktrees: { ...value.worktrees, cleanup: cleanup as 'off' | 'safe' } })} />
              </Section>
              <SwitchField label={t('worktreeDeleteBranch')} hint={t('worktreeDeleteBranchHint')} checked={value.worktrees.deleteBranch}
                onChange={deleteBranch => edit({ worktrees: { ...value.worktrees, deleteBranch } })} />
              <SwitchField label={t('worktreeReuse')} hint={t('worktreeReuseHint')} checked={value.worktrees.reuse}
                onChange={reuse => edit({ worktrees: { ...value.worktrees, reuse } })} />
              <Field label={t('worktreeCreateHook')} hint={t('worktreeCreateHookHint')}>
                <textarea className="dt-textarea dt-mono" rows={2} maxLength={LIMITS.worktreeHook} spellCheck={false}
                  value={value.worktrees.hooks.create}
                  onChange={event => edit({ worktrees: { ...value.worktrees, hooks: { ...value.worktrees.hooks, create: event.target.value } } })} />
              </Field>
              <Field label={t('worktreeRemoveHook')} hint={t('worktreeRemoveHookHint')}>
                <textarea className="dt-textarea dt-mono" rows={2} maxLength={LIMITS.worktreeHook} spellCheck={false}
                  value={value.worktrees.hooks.remove}
                  onChange={event => edit({ worktrees: { ...value.worktrees, hooks: { ...value.worktrees.hooks, remove: event.target.value } } })} />
              </Field>
            </Section>
          </div>
          <Field label={t('blockedCommands')} hint={t('blockedCommandsHint')}>
            <Input className="dt-mono" value={value.blockedCommands} placeholder={t('blockedCommandsNone')} spellCheck={false}
              onChange={event => edit({ blockedCommands: event.target.value })} />
          </Field>
        </div>
      </Fields>
      <SaveBar {...draft} onDiscard={draft.discard} />
    </form>
    <ConfigHistory blocks={['executor', 'pause']} />
  </div>
}
