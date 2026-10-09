<script setup lang="ts">
import { ref, watch } from 'vue'
import { copy as c } from '@/composables/visualLocale'
const props = defineProps<{ fields: Array<{ label: string; value: string | number | null | undefined }>; summary?: string }>()
const copied = ref<number | null>(null)
const failed = ref(false)
watch(() => props.fields, () => { copied.value = null; failed.value = false })
async function copy(value: string | number, index: number) {
  copied.value = null; failed.value = false
  try { await navigator.clipboard.writeText(String(value)); copied.value = index }
  catch { failed.value = true }
}
</script>
<template>
  <details class="technical-details">
    <summary>{{ summary ?? c('技术详情', 'Technical details') }}</summary>
    <dl class="technical-fields"><div v-for="(field, index) in fields" :key="`${index}:${field.label}`"><dt>{{ field.label }}</dt><dd><code>{{ field.value ?? c('未报告', 'Not reported') }}</code><button v-if="field.value !== null && field.value !== undefined" class="copy-button" :aria-label="`${c('复制', 'Copy')} ${field.label}`" @click="copy(field.value, index)">{{ copied === index ? c('已复制', 'Copied') : c('复制', 'Copy') }}</button></dd></div></dl>
    <p v-if="copied !== null" class="sr-only" role="status">{{ c('已复制完整原值', 'Full source value copied') }}</p>
    <p v-if="failed" role="status">{{ c('复制不可用，请选取完整原值手动复制。', 'Copy is unavailable. Select the full value and copy it manually.') }}</p>
    <slot />
  </details>
</template>
