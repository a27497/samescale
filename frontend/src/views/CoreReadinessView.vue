<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import { onMounted, ref } from 'vue'
import { workbenchApi } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { statusLabel } from '@/utils/statusLabels'
import { readinessEvidence } from '@/utils/readinessCopy'
import type { CoreReadiness } from '@/types/workbench'
const readiness = ref<CoreReadiness | null>(null)
const loading = ref(true)
const error = ref(false)
onMounted(async () => {
  try { readiness.value = await workbenchApi.readiness() }
  catch { error.value = true } finally { loading.value = false }
})
</script>
<template>
  <section>
    <div class="page-heading"><div><h2>核心就绪度</h2><p>按已保存证据检查发布条件；此页不会创建版本标签。</p></div><StatusBadge :value="readiness?.status ?? 'NOT_REPORTED'" /></div>
    <PageState v-if="loading" kind="loading">正在读取就绪度证据…</PageState>
    <div v-else-if="error || !readiness" class="panel">
      <PageState kind="error" reload>暂时无法读取就绪度证据。可能是后端服务未连接、工作区缺少发布证据，或证据读取失败；目前无法确认具体原因。</PageState>
      <h3>下一步</h3><p>请先检查本地后端服务与工作区配置，再重新加载。也可先浏览已有运行或公开演示；缺少就绪度证据不能视为验收通过。</p>
      <div class="toolbar"><RouterLink class="secondary-button" to="/settings">查看设置</RouterLink><RouterLink class="secondary-button" to="/experiments">查看已有实验</RouterLink><RouterLink class="table-link" to="/demo">查看公开演示 →</RouterLink></div>
    </div>
    <template v-else>
      <div class="notice">任何要求受阻、未报告或尚未核验时，核心发布条件都尚未满足。缺少证据不能算作通过。</div>
      <div class="panel">
        <p class="notice">此处同时展示冻结发布快照与当前工作区检查，两者属于不同证据范围。冻结记录保留原始来源，不代表当前实验注册表已运行相同检查；仅在来源有记录时展示生成时间。</p>
        <PageState v-if="!readiness.checks.length" kind="empty">暂无就绪检查项。请由操作员检查服务端发布证据配置，再重新加载；可以先查看已有运行。</PageState>
        <div v-else class="readiness-cards"><article v-for="check in readiness.checks" :key="check.key" class="panel">
          <h3 :title="check.label"><span>{{ statusLabel(check.key) }}</span> <StatusBadge :value="check.status" /></h3>
          <p v-if="check.evidence_scope === 'FROZEN_RELEASE_SNAPSHOT'">冻结发布快照 · <RouterLink class="table-link" to="/judgelab">查看当前 JudgeLab 校准 →</RouterLink></p>
          <p>{{ readinessEvidence(check.evidence) }}</p>
          <details><summary>查看证据来源与原始记录</summary><dl class="definition-list">
            <dt>证据 / 报告 ID</dt><dd>{{ check.source_id ?? '未报告' }}</dd><dt>快照 / 版本</dt><dd>{{ check.snapshot ?? '未报告' }}</dd><dt>生成时间</dt><dd>{{ check.generated_at ?? '未报告' }}</dd><dt>仓库产物 / 摘要</dt><dd class="technical">{{ check.artifact_reference ?? '未报告' }}</dd>
          </dl><RouterLink v-if="check.source_route" class="table-link" :to="check.source_route">打开已保存报告 →</RouterLink><p v-else class="muted">如有仓库产物引用，可按路径核对原始记录；冻结证据不属于当前实验注册表。</p><p>{{ check.label }}</p><p>{{ check.evidence }}</p><code>{{ check.key }} · {{ check.status }}</code></details>
        </article></div>
      </div>
      <div class="panel"><div class="panel-title"><h3>待解决项</h3><span>{{ readiness.blockers.length }} 项</span></div><div v-if="readiness.blockers.length" class="toolbar"><span v-for="blocker in readiness.blockers" :key="blocker" :title="blocker">{{ statusLabel(blocker) }}</span></div><p v-else class="muted">未列出阻碍项。是否就绪仍以本页整体状态及证据为准。</p><p v-if="readiness.blockers.length" class="muted">请先核对对应检查项的缺失证据和来源。当前 Judge 校准请到 JudgeLab 查看；发布记录需由操作员补充。</p></div>
    </template>
  </section>
</template>
