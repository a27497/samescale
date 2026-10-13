<script setup lang="ts">
import { sourceCopy } from '@/utils/sourceCopy'
import { copy as c } from '@/composables/visualLocale'
defineProps<{ text: string | null | undefined }>()
</script>
<template>
  <div class="source-text"><p>{{ text ? sourceCopy(text) : c('未报告', 'Not reported') }}</p><details v-if="text"><summary>{{ c('查看保存原文', 'View saved source') }}</summary><p>{{ text }}</p></details></div>
</template>
