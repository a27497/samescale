<script setup lang="ts">
import { computed } from 'vue'
import { copy as c } from '@/composables/visualLocale'
import { experimentOption } from '@/utils/displayIdentity'
import type { ExperimentSummary } from '@/types/workbench'
const props = defineProps<{ modelValue: string; experiments: ExperimentSummary[]; label: string; disabled?: boolean; testId?: string; loading?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; change: [] }>()
const unknown = computed(() => props.modelValue && !props.experiments.some(item => item.experiment_id === props.modelValue))
function change(event: Event) { emit('update:modelValue', (event.target as HTMLInputElement).value.trim()); emit('change') }
</script>
<template>
  <div class="experiment-picker"><label><span class="evidence-label">{{ label }}</span><select :value="modelValue" :disabled="disabled" :aria-label="label" :data-test="testId" @change="change"><option value="">{{ c('选择实验', 'Select an experiment') }}</option><option v-if="unknown" :value="modelValue">{{ loading ? c('已预填实验（名称读取中）', 'Prefilled experiment (loading name)') : c('已预填实验（名称未报告）', 'Prefilled experiment (name not reported)') }}</option><option v-for="item in experiments" :key="item.experiment_id" :value="item.experiment_id">{{ experimentOption(item, experiments) }}</option></select></label><details class="picker-identity"><summary>{{ c('查看或输入实验 ID', 'View or enter experiment ID') }}</summary><input :value="modelValue" :disabled="disabled" :aria-label="`${label} ID`" :placeholder="c('粘贴完整实验 ID', 'Paste the full experiment ID')" @change="change" /></details></div>
</template>
