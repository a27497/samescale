<script setup lang="ts">
import { computed } from 'vue'
import { copy as c } from '@/composables/visualLocale'
const props = withDefaults(defineProps<{ value: string; localized?: boolean; context?: 'generic' | 'run' | 'event' | 'verifier' | 'experiment' }>(), { localized: false, context: 'generic' })
const labels: Record<string, [string, string]> = {
  failed_subject: ['主体运行失败', 'Subject run failed'], completed: ['已结束', 'Completed'],
  queued: ['等待运行', 'Queued'], running: ['运行中', 'Running'], failed: ['运行失败', 'Run failed'], cancelled: ['已取消', 'Cancelled'],
  HISTORICAL_REAL: ['历史真实调查', 'Historical real investigation'], CURRENT_SESSIONS: ['当前调查会话', 'Current sessions'],
  THREAD_STARTED: ['会话开始', 'Thread started'], TURN_STARTED: ['回合开始', 'Turn started'], TURN_COMPLETED: ['回合结束', 'Turn completed'],
  AGENT_MESSAGE: ['Agent 消息', 'Agent message'], COMMAND_EXECUTION: ['命令执行', 'Command execution'], TOOL_CALL: ['工具调用', 'Tool call'], REASONING_PRESENT: ['含私有推理', 'Private reasoning present'],
  DIGEST_ONLY: ['仅有摘要对照', 'Digest comparison only'], NOT_AVAILABLE: ['不可用', 'Unavailable'], IMMUTABLE_EXPERIMENT: ['保存的实验记录', 'Persisted experiment record'],
  'DURABLE TERMINAL': ['已保存终态', 'Saved terminal state'], 'POLLING POSTGRES': ['读取运行状态', 'Reading run status'],
  succeeded: ['执行完成', 'Execution completed'], timeout: ['执行超时', 'Execution timed out'],
  INFORMAL: ['非正式证据', 'Informal evidence'], SMOKE: ['烟测证据', 'Smoke evidence'], FORMAL: ['正式证据', 'Formal evidence'],
  CAPABILITY_FAILURE: ['任务未通过', 'Capability failure'], PROVIDER_INFRASTRUCTURE: ['Provider 基础设施异常', 'Provider infrastructure failure'],
  VERIFIER_INFRASTRUCTURE: ['Verifier 基础设施异常', 'Verifier infrastructure failure'], CONTROL_DRIFT: ['控制条件变化', 'Control drift'],
  BUDGET_EXHAUSTION: ['预算耗尽', 'Budget exhaustion'], INCOMPLETE_PROVIDER_OUTPUT: ['Provider 输出不完整', 'Incomplete provider output'], UNACQUIRED_SLOT: ['未收集观察', 'Unacquired slot'],
  capability_fail: ['任务未通过', 'Task failed'], capability_pass: ['任务通过', 'Task passed'], infra_failure: ['基础设施失败', 'Infrastructure failure'],
  CAPABILITY: ['任务能力', 'Capability'], INFRASTRUCTURE: ['基础设施', 'Infrastructure'], UNVERIFIED_CLAIM: ['未经核验的自报', 'Unverified claim'],
  VERIFIED_FAIL: ['独立验收未通过', 'Verified failure'], VERIFIED_PASS: ['独立验收通过', 'Verified pass'],
  FIXTURE_OFFLINE: ['固定离线样例', 'Offline fixture'], READ_ONLY: ['只读', 'Read-only'],
  NOT_REPORTED: ['未报告', 'Not reported'], NOT_VERIFIED: ['尚未核验', 'Not verified'], NOT_RUN: ['未运行', 'Not run'],
  COMPARABLE: ['可比', 'Comparable'], PARTIALLY_COMPARABLE: ['部分可比', 'Partially comparable'], NOT_COMPARABLE: ['不可比', 'Not comparable'],
  PERSISTED_EXECUTION_UNVERIFIED: ['已保存 · 来源未核验', 'Saved · source unverified'], UNVERIFIED_SOURCE: ['来源未核验', 'Source unverified'],
  VERIFIED_FACT: ['已核验事实', 'Verified fact'], HYPOTHESIS: ['待验证假设', 'Hypothesis'],
  FILE_CHANGE: ['文件变化事件', 'File-change event'], FULL_STREAM: ['完整事件流', 'Full event stream'], FINAL_OUTPUT_ONLY: ['仅最终输出', 'Final output only'],
  REPORTED: ['已报告', 'Reported'], PASSED: ['通过', 'Passed'], FAILED: ['未通过', 'Failed'],
  IMPROVED: ['描述性上升', 'Descriptively higher'], DECREASED: ['描述性下降', 'Descriptively lower'], UNCHANGED: ['描述性持平', 'Descriptively unchanged'],
}
const legacy: Record<string, string> = { failed_subject: 'Subject run failed', capability_fail: 'Task failed', capability_pass: 'Task passed', infra_failure: 'Infrastructure failure', completed: 'Completed', FAIL: 'Verifier failed', PASS: 'Verifier passed', VERIFIED_FAIL: 'Verified failure', VERIFIED_PASS: 'Verified pass', FIXTURE_OFFLINE: 'Offline fixture', PERSISTED_EXECUTION_UNVERIFIED: 'Saved execution · source unverified', UNVERIFIED_SOURCE: 'Source unverified' }
const contextual: Record<string, Record<string, [string, string]>> = {
  run: { completed: ['运行已结束', 'Run completed'], failed: ['运行失败', 'Run failed'], running: ['运行中', 'Running'] },
  experiment: { completed: ['实验已结束', 'Experiment completed'], failed: ['实验运行失败', 'Experiment execution failed'], running: ['实验运行中', 'Experiment running'] },
  event: { completed: ['事件已结束', 'Event completed'], succeeded: ['事件执行完成', 'Event execution completed'], failed: ['事件执行失败', 'Event execution failed'], running: ['事件进行中', 'Event in progress'], in_progress: ['事件进行中', 'Event in progress'], cancelled: ['事件已取消', 'Event cancelled'], timeout: ['事件超时', 'Event timed out'] },
  verifier: { succeeded: ['验收执行已结束', 'Verifier execution completed'], completed: ['验收执行已结束', 'Verifier execution completed'], failed: ['验收执行失败', 'Verifier execution failed'], timeout: ['验收执行超时', 'Verifier execution timed out'], NOT_RUN: ['验收未运行', 'Verifier not run'] },
}
const label = computed(() => { const pair = contextual[props.context]?.[props.value] ?? labels[props.value]; return props.localized && pair ? c(...pair) : legacy[props.value] ?? (props.localized ? c('未识别状态', 'Unknown status') : props.value) })
const tone = computed(() => {
  if (['COMPARABLE','FORMAL','QUALIFIED_FOR_SUITE','READY','capability_pass','VERIFIED_PASS','PASS','PASSED'].includes(props.value)) return 'good'
  if (['NOT_QUALIFIED','NOT_READY','BLOCKED','failed','failed_subject','capability_fail','infra_failure','VERIFIED_FAIL','FAIL','FAILED'].includes(props.value)) return 'bad'
  if (['NOT_COMPARABLE','PARTIALLY_COMPARABLE','INFORMAL','HYPOTHESIS'].includes(props.value)) return 'warn'
  return 'neutral'
})
</script>
<template><span class="status-pill" :class="tone" :data-status="value" :data-context="context"><span>{{ label }}</span></span></template>
