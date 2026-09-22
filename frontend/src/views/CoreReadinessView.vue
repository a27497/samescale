<script setup lang="ts">
import { t } from '@/composables/i18n'
import { onMounted, ref } from 'vue'

import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import type { CoreReadiness } from '@/types/workbench'

const readiness = ref<CoreReadiness | null>(null)
const loading = ref(true)
const error = ref(false)
async function load() {
  loading.value = true; error.value = false

  try { readiness.value = await workbenchApi.readiness() }
  catch { error.value = true } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading"><div><h2>{{ t('就绪检查') }}</h2><p>{{ t('根据已有证据检查项目就绪状态，不创建发布标签。') }}</p></div><StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" /></div>
    <button v-if="error && !loading" class="secondary-button retry-button" @click="load">{{ t('重新加载') }}</button>
    <div v-if="loading" class="loading-state">{{ t('正在读取检查结果…') }}</div>
    <div v-else-if="error || !readiness" class="error-state">{{ t('暂时无法读取就绪检查。请检查本地服务；此状态不代表检查通过。') }}</div>
    <template v-else>
      <p>{{ t('冻结历史 Judge 证据与当前工作区校准记录分别检查；历史已验证不代表当前工作区已运行或已就绪。') }}</p>
      <div class="notice">{{ t('存在阻断、未报告或未验证的要求时，项目仍未就绪。') }}</div>
      <div class="panel"><table class="data-table"><thead><tr><th>{{ t('检查项') }}</th><th>{{ t('状态') }}</th><th>{{ t('证据说明') }}</th></tr></thead><tbody><tr v-for="check in readiness.checks" :key="check.key"><td><strong>{{ t(check.key === 'JUDGE_EVIDENCE' ? '冻结历史 Judge 证据' : check.key === 'JUDGE_CALIBRATION' ? '当前工作区校准证据' : check.label) }}</strong><div class="technical muted">{{ check.key }}</div></td><td><StatusBadge :value="check.status" /></td><td>{{ check.evidence }}</td></tr></tbody></table></div>
      <div class="panel"><div class="panel-title"><h3>{{ t('阻断项') }}</h3><span>{{ readiness.blockers.length }}</span></div><div class="toolbar"><StatusBadge v-for="blocker in readiness.blockers" :key="blocker" :value="blocker" /></div></div>
    </template>
  </section>
</template>
