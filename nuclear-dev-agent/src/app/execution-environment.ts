/** Execution environment variables exposed to prepare commands and documented in worker Session instructions; never contains credentials. */
import { join } from 'node:path'
import type { Ticket, Trigger } from '../core/index.ts'
import type { Deployment } from '../deployment.ts'
import type { Settings } from '../policy.ts'
import type { Localized, VariableSpec } from '../sources/kind.ts'
import type { SourceRegistry } from '../sources/registry.ts'
import { controlScript } from '../nuclear/index.ts'

/** Variables registered by the Executor; `ticket` entries are populated only when a ticket is present. */
export const EXECUTOR_VARIABLES: readonly (VariableSpec & { ticket?: true })[] = [
  { key: 'DSH_NUCLEAR_DEV_AGENT_DIR', ticket: true, description: { zh: '这个工单的执行目录；执行器 Session 在其中工作', en: 'This ticket\'s directory; the executor Session works in it' } },
  { key: 'DSH_NUCLEAR_DEV_AGENT_NAME', ticket: true, description: { zh: '工单的短名，也是执行目录的名字', en: 'The ticket\'s short name, also its directory\'s name' } },
  { key: 'DSH_NUCLEAR_DEV_AGENT_TICKET', ticket: true, description: { zh: '工单 id', en: 'The ticket id' } },
  { key: 'DSH_NUCLEAR_DEV_AGENT_BLOCKED_COMMANDS', description: { zh: '这个执行环境禁止调用的命令，以空格分隔；不要运行它们', en: 'Commands blocked in this execution environment, separated by spaces; never run them' } },
  { key: 'DSH_NUCLEAR_DEV_AGENT_KIT', description: { zh: '本机 nuclear-dev-kit 的绝对路径；七阶段门禁由它的 nuclearlib.py 判定，为空表示这套安装没接入核能流程', en: 'Absolute path of this machine\'s nuclear-dev-kit, whose nuclearlib.py judges the seven stages; empty when this installation has no nuclear flow' } },
  { key: 'DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL', description: { zh: '门禁命令行的绝对路径；阶段开工前先跑它的只读检查，门禁判定只认它', en: 'Absolute path of the gate command line; run its read-only check before stage work, as only it judges a stage' } },
]
export interface Variable { key: string; value: string; description: Localized; owner: string }

export const executionRoot = (settings: Settings, stateDir: string): string => settings.executor.directory || join(stateDir, 'work')

/** Lists all declared variables grouped by owner; `enabled` is false for Sources that are currently switched off. */
export function declaredVariables(sources: SourceRegistry, settings?: Settings): { owner: string; enabled: boolean; variables: readonly VariableSpec[] }[] {
  const on = new Set(sources.environments(settings).map(item => item.kind.kind))
  return [{ owner: 'executor', enabled: true, variables: EXECUTOR_VARIABLES },
    ...sources.declarations().map(({ kind, variables }) => ({ owner: kind, enabled: on.has(kind), variables }))]
}

export function environmentOf(input: { deployment: Deployment; sources: SourceRegistry; settings: Settings; ticket?: { id: string; name: string; directory: string }; trigger?: Trigger }): Variable[] {
  const { deployment, sources, settings, ticket, trigger } = input
  // The kit is deployment state, not a Ticket's: every Session of this installation sees the same gate command line.
  const kitPath = deployment.nuclear?.kitPath ?? ''
  const executor: Record<string, string> = { DSH_NUCLEAR_DEV_AGENT_BLOCKED_COMMANDS: settings.executor.blockedCommands.join(' '),
    DSH_NUCLEAR_DEV_AGENT_KIT: kitPath, DSH_NUCLEAR_DEV_AGENT_NUCLEARCTL: kitPath ? controlScript(kitPath) : '', ...ticket ? { DSH_NUCLEAR_DEV_AGENT_DIR: ticket.directory, DSH_NUCLEAR_DEV_AGENT_NAME: ticket.name, DSH_NUCLEAR_DEV_AGENT_TICKET: ticket.id } : {} }
  const result: Variable[] = EXECUTOR_VARIABLES.filter(spec => !spec.ticket || ticket).map(spec => ({ key: spec.key, value: executor[spec.key] ?? '', description: spec.description, owner: 'executor' }))
  for (const { kind, environment, config } of sources.environments(settings)) {
    const values = environment.values({ deployment, config, ...trigger ? { trigger } : {} })
    for (const spec of environment.variables) result.push({ key: spec.key, value: values[spec.key] ?? '', description: spec.description, owner: kind.kind })
  }
  return result
}

/** Combines a ticket's fixed directory, name, and origin trigger with the deployment's current settings. */
export function ticketEnvironment(input: { deployment: Deployment; sources: SourceRegistry; settings: Settings; ticket: Ticket; trigger?: Trigger }) {
  const { ticket, trigger, ...rest } = input
  const values = { id: ticket.id, name: ticket.execution?.name ?? '', directory: ticket.execution?.directory ?? '' }
  return environmentOf({ ...rest, ticket: values, ...trigger ? { trigger } : {} })
}
export function environmentLines(variables: Variable[]): string {
  return variables.map(variable => `- ${variable.key} = ${JSON.stringify(variable.value)}: ${variable.description.en}.`).join('\n')
}
