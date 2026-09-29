<script setup lang="ts">
withDefaults(defineProps<{ kind: 'loading' | 'empty' | 'error'; reload?: boolean }>(), { reload: false })
function reloadPage() { window.location.reload() }
</script>

<template>
  <div :class="`${kind}-state`" :role="kind === 'error' ? 'alert' : 'status'" :aria-busy="kind === 'loading' ? true : undefined">
    <p class="state-message"><slot /></p>
    <div v-if="reload && kind === 'error'" class="state-actions">
      <button type="button" class="secondary-button" @click="reloadPage">重新加载页面</button>
      <RouterLink class="table-link" to="/analyst">返回开始调查</RouterLink>
    </div>
  </div>
</template>
