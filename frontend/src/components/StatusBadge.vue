<script setup lang="ts">
import { computed } from 'vue'
import { copy as c } from '@/composables/visualLocale'
const props = withDefaults(defineProps<{ value: string; localized?: boolean }>(), { localized: false })
const labels: Record<string, [string, string]> = {
  failed_subject: ['主体运行失败', 'Subject run failed'], completed: ['运行已结束', 'Run completed'],
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
const label = computed(() => { const pair = labels[props.value]; return props.localized && pair ? c(...pair) : legacy[props.value] ?? props.value })
const tone = computed(() => {
  if (['COMPARABLE','FORMAL','QUALIFIED_FOR_SUITE','READY','completed','capability_pass','VERIFIED_PASS','PASS','PASSED'].includes(props.value)) return 'good'
  if (['NOT_QUALIFIED','NOT_READY','BLOCKED','failed','failed_subject','capability_fail','infra_failure','VERIFIED_FAIL','FAIL','FAILED'].includes(props.value)) return 'bad'
  if (['NOT_COMPARABLE','PARTIALLY_COMPARABLE','INFORMAL','HYPOTHESIS'].includes(props.value)) return 'warn'
  return 'neutral'
})
</script>
<template><span class="status-pill" :class="tone" :title="value" :data-status="value"><span>{{ label }}</span><code v-if="localized && label !== value" class="status-code">{{ value }}</code></span></template>
