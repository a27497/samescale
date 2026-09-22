<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { t } from '@/composables/i18n'
import type { ProductMode } from '@/composables/productContext'

const emit = defineEmits<{ mode: [value: ProductMode] }>()

const mode = ref<'demo' | 'workspace' | 'unknown'>('unknown')
const state = ref<'checking' | 'ready' | 'unavailable'>('checking')
async function check() {
  state.value = 'checking'
  let metadataReady = false
  try {
    const response = await fetch('/api/product', { signal: AbortSignal.timeout(5000) })
    if (!response.ok) throw new Error('mode unavailable')
    const product = await response.json()
    if (!['demo', 'workspace'].includes(product.mode)) throw new Error('invalid mode')
    metadataReady = true
    mode.value = product.mode
    emit('mode', mode.value)
    const health = await fetch(mode.value === 'demo' ? '/api/demo/health' : '/api/health', { signal: AbortSignal.timeout(5000) })
    const body = await health.json()
    state.value = health.ok && (mode.value === 'demo' ? body.mode === 'demo' && body.status === 'ready' : body.status === 'ok' && body.database === 'ok') ? 'ready' : 'unavailable'
  } catch {
    state.value = 'unavailable'
    if (!metadataReady) { mode.value = 'unknown'; emit('mode', 'unknown') }
  }
}
onMounted(check)
</script>

<template>
  <details class="product-status">
    <summary :aria-label="t('运行模式')"><span class="service-dot" :class="state" aria-hidden="true" /><span>{{ t(state === 'checking' ? '连接中…' : state === 'unavailable' ? '服务异常' : mode === 'demo' ? '演示模式' : '本地工作区') }}</span></summary>
    <div class="status-detail" aria-live="polite">
      <p v-if="state === 'unavailable'" role="alert">{{ t('连接失败，请检查服务后重试。') }}</p>
      <p v-else-if="state === 'ready'">{{ t('服务正常') }}</p>
      <p v-if="mode === 'demo'">{{ t('打开完整工作区：') }}<code>samescale up</code></p>
      <button :disabled="state === 'checking'" @click="check">{{ t('重新检查') }}</button>
    </div>
  </details>
</template>

<style scoped>
.product-status { color: var(--muted); font: var(--type-caption); margin-top: 10px; overflow-wrap: anywhere; }
summary { display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 10px; list-style: none; }summary::-webkit-details-marker { display: none; }
.service-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #8a9199; }.service-dot.ready { background: #518569; }.service-dot.unavailable { background: #ac583f; }
.status-detail { padding: 0 10px 10px; }p { margin: 6px 0; }code { display: block; }
button { border: 0; background: transparent; color: var(--link); cursor: pointer; font: inherit; padding: 6px 0; }button:disabled { opacity: .5; cursor: default; }
</style>
