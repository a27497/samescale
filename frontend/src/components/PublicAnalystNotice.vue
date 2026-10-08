<script setup lang="ts">
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
</script>
<template>
  <div class="public-analyst-notice" role="status">
    <strong>当前为只读 Public Demo</strong>
    <p>持久化会话仅限本地 / 私有工作区。此处不能创建或恢复会话、进行 Real 调查、保存或审批方案。</p>
    <RouterLink class="table-link" to="/demo">查看公开演示的证据路径 →</RouterLink>
    <div v-if="!compact" class="notice-alternatives">
      <RouterLink class="table-link" to="/analyst?example=offline">运行 Offline Fake 演示 →</RouterLink>
      <RouterLink class="table-link" to="/analyst?example=historical">阅读历史 Real 只读报告 →</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.public-analyst-notice { font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; }
.public-analyst-notice strong { color: var(--ink); }
.public-analyst-notice p { color: var(--muted); margin: 10px 0 16px; }
.public-analyst-notice a { display: block; width: fit-content; min-height: 44px; padding-block: 8px; }
.notice-alternatives { display: grid; gap: 2px; }
</style>
