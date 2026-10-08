<script setup lang="ts">
import { copy as c } from '@/composables/visualLocale'
withDefaults(defineProps<{ kind: 'loading' | 'empty' | 'error'; reload?: boolean }>(), { reload: false })
function reloadPage() { window.location.reload() }
</script>

<template>
  <div :class="`${kind}-state`" :role="kind === 'error' ? 'alert' : 'status'" :aria-busy="kind === 'loading' ? true : undefined">
    <p class="state-message"><slot /></p>
    <div v-if="reload && kind === 'error'" class="state-actions">
      <button type="button" class="secondary-button" @click="reloadPage">{{ c('重新加载页面', 'Reload page') }}</button>
      <RouterLink class="table-link" to="/analyst">{{ c('返回调查首页', 'Back to investigation home') }}</RouterLink>
    </div>
  </div>
</template>
