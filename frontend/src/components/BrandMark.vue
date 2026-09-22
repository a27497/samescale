<script setup lang="ts">
import mark from '@/assets/samescale-mark.svg'
</script>

<template>
  <img :src="mark" alt="" aria-hidden="true" width="64" height="64" draggable="false" class="samescale-mark">
</template>

<style scoped>
.samescale-mark { display: block; flex: none; width: 32px; height: 32px; }
</style>
