/**
 * Nuclear tab: the kit this installation runs, and every Ticket workspace's seven stages as the kit's own gate judges
 * them. The page shows what a person must decide and what the work must fix, and quotes the kit's messages verbatim.
 */
import { useState } from 'react'
import { usePoll, type NuclearProjectRow, type NuclearStageRow, type TicketNuclear } from './api.ts'
import { Button, Dot, Icon, Tag, type DotState, type TagTone } from './controls.tsx'
import { useAction, usePanel } from './provider.tsx'
import { valueLabel } from './text.ts'
import { Hint, LabelValue, LoadState, Section, StatusHead, When } from './widgets.tsx'

const DOT: Record<NuclearStageRow['state'], DotState> = { passed: 'done', 'awaiting-approval': 'warning', blocked: 'error',
  missing: 'idle' }
const TONE: Record<NuclearStageRow['state'], TagTone> = { passed: 'success', 'awaiting-approval': 'warning', blocked: 'danger',
  missing: 'quiet' }

/** One stage: the kit's verdict, its messages as written, and the signature it records. */
function StageRow({ report, compact }: { report: NuclearStageRow; compact: boolean }) {
  const { t } = usePanel()
  const [open, setOpen] = useState(false)
  const shown = open ? report.errors : report.errors.slice(0, 2)
  return <li className="dt-row">
    <Dot state={DOT[report.state]} label={valueLabel(t, 'nuclearState', report.state)} />
    <div className="dt-row-main">
      <div className="dt-row-title">
        <span>{t(`stage.${report.stage}`)}</span>
        <Tag tone={TONE[report.state]}>{valueLabel(t, 'nuclearState', report.state)}</Tag>
        {!compact && <span className="dt-hint dt-mono">{report.artifact}</span>}
      </div>
      {shown.length > 0 && <ul className="dt-list dt-hints">{shown.map((error, index) => <li key={index}
        className="dt-hint dt-mono">{error}</li>)}</ul>}
      {report.errors.length > shown.length && <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {t('nuclearAllErrors', { count: report.errors.length })}</Button>}
      {report.approval && <div className="dt-row-meta">
        <span>{t('nuclearApproval', { name: report.approval.approver || t('nuclearApprovalAnonymous') })}</span>
        {report.approval.date && <When at={report.approval.date} />}
      </div>}
    </div>
  </li>
}

/** The seven stages of a workspace, in the kit's order; the Ticket page shows the same rows without the artifact paths. */
export function StageRows({ stages, compact = false }: { stages: NuclearStageRow[]; compact?: boolean }) {
  return <ul className="dt-list">{stages.map(report => <StageRow key={report.stage} report={report} compact={compact} />)}</ul>
}

function Counts({ counts }: { counts: { passed: number; awaiting: number; blocked: number; missing: number; projects: number;
  complete: number } }) {
  const { t } = usePanel()
  return <div className="dt-row-meta dt-status-line">
    <LabelValue label={t('nuclearCountProjects')} value={counts.projects} />
    <LabelValue label={valueLabel(t, 'nuclearState', 'passed')} value={counts.passed} />
    <LabelValue label={valueLabel(t, 'nuclearState', 'awaiting-approval')} value={counts.awaiting} />
    <LabelValue label={valueLabel(t, 'nuclearState', 'blocked')} value={counts.blocked} />
    <LabelValue label={valueLabel(t, 'nuclearState', 'missing')} value={counts.missing} />
    <LabelValue label={t('nuclearCountComplete')} value={counts.complete} />
  </div>
}

/** One workspace: the project the kit recorded, its Tickets, and its stages. */
function Project({ project }: { project: NuclearProjectRow }) {
  const { t, navigate } = usePanel()
  const title = project.project?.name || project.root
  return <Section title={title} count={`${project.passed}/${project.stages.length}`}
    hint={t('nuclearProjectHint', { root: project.root })}
    action={<span className="dt-row-meta"><When at={project.checkedAt} /></span>}>
    <div className="dt-row-meta dt-status-line">
      {project.project && <>
        <LabelValue label={t('nuclearProjectId')} value={<span className="dt-mono">{project.project.id}</span>} />
        <LabelValue label={t('nuclearKitVersion')} value={project.project.kitVersion} />
        <LabelValue label={t('nuclearSafety')} value={project.project.safetyClassification} />
        <LabelValue label={t('nuclearVVLevel')} value={project.project.vvLevel} />
      </>}
      {project.tickets.map(ticket => <button key={ticket.id} type="button" className="dt-textlink"
        onClick={() => navigate({ page: 'execution', id: ticket.id })}>{ticket.title}</button>)}
    </div>
    {project.problem
      ? <Hint>{project.problem.detail}</Hint>
      : <>
        {project.gate && !project.gate.ok && <Hint>{t('nuclearGateHint', { stage: t(`stage.${project.gate.stage}`),
          count: project.gate.errors.length })}</Hint>}
        <StageRows stages={project.stages} />
      </>}
  </Section>
}

export function NuclearPage() {
  const { t, call } = usePanel()
  const { data, error, reload } = usePoll(() => call('GET nuclear'), [])
  const refresh = useAction(() => call('POST nuclear/refresh'), { reload })
  if (!data) return <LoadState error={error} loading />
  const { header } = data
  return <>
    <StatusHead hint={t('nuclearStatusIntro')} />
    {error && <LoadState error={error} loading={false} />}
    <div className="dt-row-meta dt-status-line">
      <span className="dt-status-text" data-state={header.ready ? 'ongoing' : 'warning'}>
        {header.ready ? t('nuclearKitReady') : t('nuclearKitMissing')}
      </span>
      <LabelValue label={t('nuclearKitPath')} value={<span className="dt-mono">{header.kitPath || t('empty')}</span>} />
      {header.pythonVersion && <LabelValue label={t('nuclearPython')} value={header.pythonVersion} />}
      <Button variant="outline" size="sm" icon={<Icon name="refresh" size={14} />} disabled={refresh.busy}
        onClick={() => { void refresh.run() }}>{t('nuclearRefresh')}</Button>
    </div>
    {!data.configured && <Hint>{t('nuclearOff')}</Hint>}
    {header.problem && <Hint>{header.problem.detail}</Hint>}
    {header.interpreterProblem && <p className="dt-error">{header.interpreterProblem.detail}</p>}
    {data.configured && <>
      <Hint>{t('nuclearEvidenceHint', { seconds: header.refreshSeconds })}</Hint>
      <Counts counts={data.counts} />
      {data.omitted !== undefined && <Hint>{t('nuclearOmitted', { count: data.omitted })}</Hint>}
      {data.projects.length
        ? data.projects.map(project => <Project key={project.root} project={project} />)
        : <Hint>{t('nuclearNoWorkspace')}</Hint>}
    </>}
  </>
}

/** The stage section of a Ticket page: present once the Ticket's directory holds a kit workspace. */
export function TicketStages({ nuclear }: { nuclear: TicketNuclear }) {
  const { t, navigate } = usePanel()
  return <Section title={t('nuclearStagesTitle')} count={`${nuclear.passed}/${nuclear.stages.length}`}
    hint={t('nuclearStagesHint')}
    action={<Button variant="ghost" size="sm" icon={<Icon name="chevron-right" size={14} />}
      onClick={() => navigate({ page: 'nuclear' })}>{t('nuclearOpenBoard')}</Button>}>
    {nuclear.problem
      ? <Hint>{nuclear.problem.detail}</Hint>
      : <>
        {nuclear.gate && !nuclear.gate.ok && <Hint>{t('nuclearGateHint', { stage: t(`stage.${nuclear.gate.stage}`),
          count: nuclear.gate.errors.length })}</Hint>}
        <StageRows stages={nuclear.stages} compact />
      </>}
  </Section>
}
