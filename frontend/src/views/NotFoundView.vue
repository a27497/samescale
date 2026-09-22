<script setup lang="ts">
import { t } from '@/composables/i18n'
</script>
<template>
  <section class="centered-state">
    <span class="eyebrow">{{ t('页面不存在') }}</span>
    <h2>{{ t('没有找到此页面') }}</h2>
    <p>{{ t('链接可能已失效。可以返回首页查看评测入口。') }}</p>
    <RouterLink class="primary-button" to="/">{{ t('返回首页') }}</RouterLink>
  </section>
</template>
