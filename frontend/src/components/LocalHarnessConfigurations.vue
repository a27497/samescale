<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { localConfigurationApi as api, type ConfigurationOptions, type LocalHarnessConfiguration } from '@/api/localConfiguration'
import type { ProviderModelProfile } from '@/types/registry'
import { t } from '@/composables/i18n'
const props = defineProps<{ token: string; profiles: ProviderModelProfile[] }>()
const emit = defineEmits<{ changed: [] }>()
const items = ref<LocalHarnessConfiguration[]>([])
const options = ref<ConfigurationOptions>({ model_controls: [], harness_templates: [] })
const busy = ref(false); const error = ref(''); const message = ref('')
const form = reactive({ id: '', name: '', template: '', bindings: [] as string[], enabled: true, revision: 0 })
const preset = computed(() => options.value.harness_templates.find(p => p.profile_id === form.template))
const staleBindings = computed(() => form.bindings.filter(id => !preset.value?.supported_provider_profile_ids.includes(id)))
const valid = computed(() => /^[a-z][a-z0-9-]{0,39}$/.test(form.id) && form.name.trim().length > 0 && preset.value && form.bindings.length > 0 && ((!form.enabled && form.revision > 0) || form.bindings.every(id => preset.value!.supported_provider_profile_ids.includes(id))))
let generation = 0
function reset() { Object.assign(form, { id: '', name: '', template: options.value.harness_templates[0]?.profile_id ?? '', bindings: [], enabled: true, revision: 0 }) }
function edit(item: LocalHarnessConfiguration) { Object.assign(form, { id: item.configuration_id, name: item.name, template: item.template_profile_id, bindings: [...item.profile.supported_provider_profile_ids], enabled: item.enabled, revision: item.revision }); error.value = ''; message.value = '' }
async function load() {
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  try {
    const [saved, available] = await Promise.all([api.harnesses(props.token), api.options(props.token)])
    if (current !== generation) return
    items.value = saved.items; options.value = available; reset()
  } catch { if (current === generation) { options.value = { model_controls: [], harness_templates: [] }; error.value = '运行配置读取失败，请重新读取。' } }
  finally { if (current === generation) busy.value = false }
}
async function save() {
  if (busy.value || !valid.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  try {
    const item = await api.saveHarness(form.id, { name: form.name.trim(), expected_revision: form.revision, template_profile_id: form.template, provider_profile_ids: [...form.bindings], enabled: form.enabled }, props.token)
    if (current !== generation) return
    items.value = [...items.value.filter(i => i.configuration_id !== item.configuration_id), item]; edit(item); message.value = '运行配置已保存。保存不会执行评测。'; emit('changed')
  } catch { if (current === generation) error.value = '保存未确认。请重新读取，并检查版本或模型兼容性。' }
  finally { if (current === generation) busy.value = false }
}
// Refresh available bindings after model/connection writes without discarding an edited form.
watch(() => props.profiles, async profiles => {
  if (!profiles.length || busy.value) return
  const current = generation
  try { const available = await api.options(props.token); if (current === generation) options.value = available }
  catch { if (current === generation) { options.value = { model_controls: [], harness_templates: [] }; error.value = '运行配置读取失败，请重新读取。' } }
})
onMounted(load); onBeforeUnmount(() => generation++)
</script>
<template>
  <section class="local-harnesses" aria-labelledby="local-harnesses-title">
    <h4 id="local-harnesses-title">{{ t('本地运行配置') }}</h4>
    <p>{{ t('从已注册预设选择运行版本、推理档位和兼容模型。工具、网络权限与执行方式保持预设约束。') }}</p>
    <div class="actions"><button class="secondary-button" :disabled="busy" @click="load">{{ t('重新读取运行配置') }}</button><button class="secondary-button" :disabled="busy" @click="reset">{{ t('新增运行配置') }}</button></div>
    <p v-if="error" role="alert" class="error-state">{{ t(error) }}</p><p v-if="message" role="status">{{ t(message) }}</p>
    <ul><li v-for="item in items" :key="item.configuration_id"><button :disabled="busy" @click="edit(item)">{{ item.name }} · v{{ item.revision }} · {{ t(item.enabled ? '已启用' : '已停用') }}</button><code>{{ item.profile.profile_id }}</code></li></ul>
    <form @submit.prevent="save"><fieldset :disabled="busy"><legend>{{ t(form.revision ? '编辑运行配置' : '新增运行配置') }}</legend>
      <label>{{ t('运行配置 ID') }}<input v-model="form.id" :disabled="form.revision > 0" pattern="[a-z][a-z0-9\-]{0,39}" maxlength="40" required></label>
      <label>{{ t('运行配置名称') }}<input v-model="form.name" maxlength="100" required></label>
      <label>{{ t('运行预设') }}<select v-model="form.template" :aria-label="t('运行预设')" @change="form.bindings = []"><option v-for="p in options.harness_templates" :key="p.profile_id" :value="p.profile_id">{{ p.profile_id }} · {{ p.version }}</option></select></label>
      <p v-if="preset">{{ t('预设工具') }}：{{ preset.tool_surface.join(', ') || t('无工具') }} · {{ t('推理强度') }}：{{ preset.reasoning_effort ?? t('沿用模型') }}</p>
      <fieldset class="bindings"><legend>{{ t('绑定模型版本') }}</legend><label v-for="id in preset?.supported_provider_profile_ids" :key="id"><input v-model="form.bindings" type="checkbox" :value="id">{{ id }}</label><label v-for="id in staleBindings" :key="id"><input v-model="form.bindings" type="checkbox" :value="id">{{ t('失效绑定') }}：{{ id }}</label></fieldset>
      <p v-if="form.bindings.some(id => !preset?.supported_provider_profile_ids.includes(id))" role="alert">{{ t('绑定已失效，请重新选择当前模型版本。') }}</p>
      <label class="checkbox"><input v-model="form.enabled" type="checkbox">{{ t('启用运行配置') }}</label>
      <button class="primary-button" :disabled="!valid">{{ t('保存运行配置') }}</button>
    </fieldset></form>
  </section>
</template>
<style scoped>
.local-harnesses { margin-top:28px; padding-top:20px; border-top:1px solid var(--line); }p { color:var(--muted); font:var(--type-caption); }
.actions { display:flex; flex-wrap:wrap; gap:12px; }form,fieldset,label { display:grid; gap:12px; min-width:0; }fieldset { border:1px solid var(--line); border-radius:8px; padding:16px; }
input,select { width:100%; min-width:0; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; padding:10px; background:var(--panel); color:var(--ink); font:var(--type-control); }
.bindings label,.checkbox { display:flex; align-items:center; overflow-wrap:anywhere; }.bindings input,.checkbox input { width:auto; }ul { list-style:none; padding:0; }li { display:grid; gap:8px; margin:12px 0; overflow-wrap:anywhere; }
li button { text-align:left; padding:10px; background:var(--panel); border:1px solid var(--line); border-radius:6px; color:var(--ink); }button { overflow-wrap:anywhere; max-width:100%; }code { font-size:12px; }
</style>
