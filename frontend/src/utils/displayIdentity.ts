import { copy as c } from '@/composables/visualLocale'
import type { ExperimentSummary } from '@/types/workbench'
import { experimentDisplayName } from './evidenceCopy'

// Presentation only: routes, search, citations and downloads keep their original keys.
export function identityKey(id: string, peers: string[] = []): string {
  const token = (value: string) => {
    const stripped = value.replace(/^(run-|sha256:)/, '')
    return /^[a-f0-9]{32,}$/i.test(stripped) ? stripped : [...stripped].reverse().join('')
  }
  const own = token(id)
  let size = Math.min(8, own.length)
  while (size < own.length && peers.some(other => other !== id && token(other).slice(0, size) === own.slice(0, size))) size++
  const stripped = id.replace(/^(run-|sha256:)/, '')
  return /^[a-f0-9]{32,}$/i.test(stripped) ? own.slice(0, size) : [...own.slice(0, size)].reverse().join('')
}
const tasks: Record<string, [string, string]> = {
  'micro-typescript-clamp': ['TypeScript 边界修复', 'TypeScript clamp fix'],
  'micro-python-clamp': ['Python 边界修复', 'Python clamp fix'],
  'micro-python-normalize': ['Python 规范化', 'Python normalization'],
  'core-java-deduplicate': ['Java 去重任务', 'Java deduplication'],
}
export function taskName(id: string): string {
  const pair = tasks[id]
  return pair ? c(...pair) : id.length <= 32 ? id : `${c('任务', 'Task')} · ${identityKey(id)}`
}
export function configName(id: string, peers: string[] = []): string {
  if (id === 'fixture-codex') return c('Codex 离线配置', 'Offline Codex configuration')
  return `${c('配置', 'Configuration')} · ${identityKey(id, peers)}`
}
export function experimentName(item: Pick<ExperimentSummary, 'name' | 'provenance'>): string {
  const names: Record<string, [string, string]> = {
    'Public Demo — offline fixture baseline': ['公开演示 · 基线', 'Public demo · Baseline'],
    'Public Demo — offline fixture candidate': ['公开演示 · 候选', 'Public demo · Candidate'],
  }
  const name = experimentDisplayName(item.name, item.provenance)
  const pair = item.provenance === 'FIXTURE_OFFLINE' ? names[name] : undefined
  return pair ? c(...pair) : name
}
export function experimentOption(item: ExperimentSummary, peers: ExperimentSummary[]): string {
  const name = experimentName(item)
  return peers.some(other => other.experiment_id !== item.experiment_id && experimentName(other) === name)
    ? `${name} · ${identityKey(item.experiment_id, peers.map(other => other.experiment_id))}` : name
}
export function runName(run: { run_id: string; task_id: string; repeat_index?: number; attempt?: number }, peers: string[] = []): string {
  return `${taskName(run.task_id)}${run.repeat_index === undefined ? '' : ` · ${c(`第 ${run.repeat_index + 1} 次`, `Repeat ${run.repeat_index + 1}`)}`}${run.attempt === undefined ? '' : ` · ${c('尝试', 'Attempt')} ${run.attempt}`} · ${identityKey(run.run_id, peers)}`
}
export function referenceName(reference: string, index: number): string {
  const prefix = reference.split(':')[0]
  const labels: Record<string, [string, string]> = { run: ['运行记录', 'Run record'], trace: ['事件来源', 'Trace source'], 'cluster-dimensions': ['分类依据', 'Classification source'], cell: ['配置证据', 'Configuration evidence'], ablation: ['消融证据', 'Ablation evidence'] }
  const pair = labels[prefix ?? '']
  return `${pair ? c(...pair) : c('证据引用', 'Evidence reference')} ${index + 1}`
}
