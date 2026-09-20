<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { localConfigurationApi, type LocalModelConfiguration, type ConnectionMetadata, type ConfigurationOptions } from '@/api/localConfiguration'
import type { ProviderModelProfile, HarnessDefinition, ProviderDefinition } from '@/types/registry'
import LocalHarnessConfigurations from '@/components/LocalHarnessConfigurations.vue'
import LocalConnections from '@/components/LocalConnections.vue'
import { t } from '@/composables/i18n'

const props = defineProps<{ profiles: ProviderModelProfile[], harnesses: HarnessDefinition[], providers: ProviderDefinition[] }>()
const emit = defineEmits<{ changed: [] }>()
const available = ref(false); const statusError = ref(false); const statusChecking = ref(true); const token = ref('')
const unlocked = ref(false); const busy = ref(false); const error = ref(''); const message = ref('')
const items = ref<LocalModelConfiguration[]>([])
const connections = ref<ConnectionMetadata[]>([])
const options = ref<ConfigurationOptions>({ model_controls: [], harness_templates: [] })
const controls = computed(() => options.value.model_controls.find(c => c.profile_id === form.template))
const purposeName = (value?: string) => value === 'ANALYST' ? 'Analyst 模型' : value === 'JUDGE' ? 'Judge 模型' : '被测模型'
function templateChanged() { form.maxOutput = controls.value?.max_output_tokens ?? ''; form.effort = ''; form.temperature = '' }

const matchingConnections = computed(() => {
  const template = templates.value.find(p => p.profile_id === form.template)
  return connections.value.filter(c => c.template_provider_id === template?.provider_id && c.protocol === template?.protocol)
})
function updateConnections(values: ConnectionMetadata[]) { connections.value = values }

const form = reactive({ purpose: 'SUBJECT' as 'SUBJECT' | 'ANALYST' | 'JUDGE', maxOutput: '' as number | '', effort: '', temperature: '' as number | '', id: '', name: '', template: '', timeout: 60, enabled: true, revision: 0, connection: '' })
const templates = computed(() => props.profiles.filter(p => !p.profile_id.startsWith('local-')
  && props.harnesses.some(h => h.harness_id === 'direct-model' && h.profiles.some(hp => hp.supported_provider_profile_ids.includes(p.profile_id)))))
const valid = computed(() => /^[a-z][a-z0-9-]{0,39}$/.test(form.id) && form.name.trim().length > 0
  && (!form.connection || matchingConnections.value.some(c => c.connection_id === form.connection))
  && controls.value !== undefined
  && (form.maxOutput === '' || (Number.isInteger(form.maxOutput) && form.maxOutput >= 1 && form.maxOutput <= controls.value.max_output_tokens))
  && (!form.effort || controls.value.reasoning_efforts.includes(form.effort))
  && (form.temperature === '' || (controls.value.temperature_supported && Number.isFinite(form.temperature) && form.temperature >= 0 && form.temperature <= 2))
  && templates.value.some(p => p.profile_id === form.template) && Number.isInteger(form.timeout) && form.timeout >= 1 && form.timeout <= 600)
let generation = 0
async function checkStatus() {
  const current = ++generation; statusError.value = false; statusChecking.value = true
  try { const result = await localConfigurationApi.status(); if (current === generation) available.value = result.enabled }
  catch { if (current === generation) { available.value = false; statusError.value = true } }
  finally { if (current === generation) statusChecking.value = false }
}
function reset() { Object.assign(form, { purpose: 'SUBJECT', maxOutput: '', effort: '', temperature: '', id: '', name: '', template: templates.value[0]?.profile_id ?? '', timeout: 60, enabled: true, revision: 0, connection: '' }); templateChanged() }
function edit(item: LocalModelConfiguration) {
  Object.assign(form, { purpose: item.purpose ?? 'SUBJECT', maxOutput: item.max_output_tokens ?? '', effort: item.reasoning_effort ?? '', temperature: item.temperature ?? '', id: item.configuration_id, name: item.name, template: item.template_profile_id, timeout: item.request_timeout_seconds, enabled: item.enabled, revision: item.revision, connection: item.connection_id ?? '' })
  error.value = ''; message.value = ''
}
function lock() { generation++; token.value = ''; unlocked.value = false; items.value = []; connections.value = []; busy.value = false; error.value = ''; message.value = ''; reset() }
async function unlock() {
  if (busy.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  try {
    const [result, limits] = await Promise.all([localConfigurationApi.list(token.value), localConfigurationApi.options(token.value)])
    if (current !== generation) return
    options.value = limits; items.value = result.items; unlocked.value = true; reset()
  } catch { if (current === generation) { items.value = []; unlocked.value = false; error.value = '无法读取本地配置，请检查管理令牌和服务后重试。' } }
  finally { if (current === generation) busy.value = false }
}
async function save() {
  if (busy.value || !valid.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  try {
    const connection = matchingConnections.value.find(c => c.connection_id === form.connection)
    const binding = connection ? { connection_id: connection.connection_id, connection_revision: connection.revision } : {}
    const item = await localConfigurationApi.save(form.id, { name: form.name.trim(), template_profile_id: form.template, request_timeout_seconds: form.timeout, enabled: form.enabled, expected_revision: form.revision, purpose: form.purpose, max_output_tokens: form.maxOutput === '' ? null : form.maxOutput, reasoning_effort: form.effort || null, temperature: form.temperature === '' ? null : form.temperature, ...binding }, token.value)
    if (current !== generation) return
    items.value = [...items.value.filter(i => i.configuration_id !== item.configuration_id), item]
    edit(item); message.value = '配置已保存。保存不会执行评测。'; emit('changed')
  } catch { if (current === generation) error.value = '保存未确认。请重新读取配置后再试，避免覆盖其他修改。' }
  finally { if (current === generation) busy.value = false }
}
onMounted(checkStatus); onBeforeUnmount(lock)
</script>

<template>
  <section class="local-models settings-section" aria-labelledby="local-models-title">
    <h3 id="local-models-title">{{ t('本地模型配置') }}</h3>
    <p>{{ t('从已支持的直接调用模板创建配置，可选择同服务商、同协议的本地连接。') }}</p>
    <p>{{ t('每次保存产生新版本；历史计划保持原样。Agent 运行时兼容性不会自动扩展。') }}</p>
    <p v-if="statusChecking" role="status">{{ t('正在读取本地编辑状态…') }}</p>
    <div v-else-if="statusError" role="alert"><p>{{ t('无法读取本地编辑状态。') }}</p><button class="secondary-button" @click="checkStatus">{{ t('重新读取') }}</button></div>
    <p v-else-if="!available">{{ t('本地编辑尚未启用，请按 README 配置本机管理令牌并重启工作区。') }}</p>
    <template v-else>
      <form v-if="!unlocked" class="local-form" @submit.prevent="unlock">
        <label>{{ t('本机管理令牌') }}<input v-model="token" type="password" autocomplete="off" :disabled="busy" required></label>
        <button class="secondary-button" :disabled="busy || !token">{{ t('解锁本地配置') }}</button>
        <small>{{ t('令牌只在当前页面内存中使用，离开页面即清除。不要填写模型 API Key。') }}</small>
      </form>
      <template v-else>
        <LocalConnections :token="token" :providers="providers" @updated="updateConnections" @changed="emit('changed')" />
        <div class="local-actions"><button class="secondary-button" :disabled="busy" @click="unlock">{{ t('重新读取') }}</button><button class="secondary-button" @click="lock">{{ t('锁定') }}</button><button class="secondary-button" :disabled="busy" @click="reset">{{ t('新增配置') }}</button></div>
        <p v-if="!items.length">{{ t('尚无本地模型配置。') }}</p>
        <ul class="local-list"><li v-for="item in items" :key="item.configuration_id"><button :disabled="busy" @click="edit(item)">{{ item.name }} · v{{ item.revision }} · {{ t(item.enabled ? '已启用' : '已停用') }}</button><code>{{ item.profile.profile_id }}</code><small>{{ t(purposeName(item.purpose)) }}</small></li></ul>
        <form class="local-form model-editor" @submit.prevent="save">
          <fieldset :disabled="busy">
            <legend>{{ t(form.revision ? '编辑配置' : '新增配置') }}</legend>
            <label>{{ t('配置 ID') }}<input v-model="form.id" :aria-label="t('配置 ID')" :disabled="form.revision > 0" pattern="[a-z][a-z0-9-]{0,39}" maxlength="40" required><small>{{ t('小写字母开头，可含数字和连字符。') }}</small></label>
            <label>{{ t('配置名称') }}<input v-model="form.name" maxlength="100" required></label>
            <label>{{ t('内置模型模板') }}<select v-model="form.template" @change="templateChanged" :aria-label="t('内置模型模板')" required><option disabled value="">{{ t('选择模板') }}</option><option v-for="p in templates" :key="p.profile_id" :value="p.profile_id">{{ p.profile_id }}</option></select></label>
            <label>{{ t('服务连接') }}<select v-model="form.connection" :aria-label="t('服务连接')"><option value="">{{ t('沿用模板连接') }}</option><option v-if="form.connection && !matchingConnections.some(c => c.connection_id === form.connection)" :value="form.connection" disabled>{{ t('连接已失效，请重新选择') }}</option><option v-for="c in matchingConnections" :key="c.connection_id" :value="c.connection_id">{{ c.name }} · v{{ c.revision }} · {{ t(c.ready_for_planning ? '本地引用可用' : '需要检查引用') }}</option></select><small>{{ t('保存将绑定所选连接的当前版本。轮换或停用后需重新绑定，旧计划保持原样。') }}</small></label>
            <label>{{ t('模型用途') }}<select v-model="form.purpose" :aria-label="t('模型用途')"><option value="SUBJECT">{{ t('被测模型') }}</option><option value="ANALYST">{{ t('Analyst 模型') }}</option><option value="JUDGE">{{ t('Judge 模型') }}</option></select></label>
            <small>{{ t('仅被测模型可用于评测计划。保存用途不会切换当前 Analyst 或 Judge。') }}</small>
            <label>{{ t('配置输出 Token 上限') }}<input v-model.number="form.maxOutput" :aria-label="t('配置输出 Token 上限')" type="number" min="1" :max="controls?.max_output_tokens" step="1"><small>{{ t('计划预算不得超过此上限；留空不额外限制。') }}</small></label>
            <label>{{ t('推理强度') }}<select v-model="form.effort" :aria-label="t('推理强度')" :disabled="!controls?.reasoning_efforts.length"><option value="">{{ t('沿用模板') }}</option><option v-for="effort in controls?.reasoning_efforts" :key="effort" :value="effort">{{ effort }}</option></select></label>
            <label v-if="controls?.temperature_supported">temperature<input v-model.number="form.temperature" aria-label="temperature" type="number" min="0" max="2" step="0.1"></label>
            <small v-else>{{ t('此模板未声明 temperature 支持。') }}</small>
            <label>{{ t('单次请求超时（秒）') }}<input v-model.number="form.timeout" type="number" min="1" max="600" step="1" required></label>
            <label class="local-checkbox"><input v-model="form.enabled" type="checkbox">{{ t('启用此配置') }}</label>
            <button class="primary-button" :disabled="!valid">{{ t('保存配置') }}</button>
          </fieldset>
        </form>
        <LocalHarnessConfigurations :token="token" :profiles="profiles" @changed="emit('changed')" />
      </template>
      <p v-if="error" class="error-state" role="alert">{{ t(error) }}</p>
      <p v-if="message" role="status">{{ t(message) }}</p>
    </template>
  </section>
</template>

<style scoped>
.local-models { border-top:1px solid var(--line); padding-top:24px; }
.local-models p, small { color:var(--muted); font:var(--type-caption); }
.local-actions { display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }
.local-form, fieldset { display:grid; gap:16px; min-width:0; }
fieldset { border:1px solid var(--line); border-radius:8px; padding:16px; }
label { display:grid; gap:8px; min-width:0; }
input, select { width:100%; min-width:0; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; padding:10px; background:var(--panel); color:var(--ink); font:var(--type-control); }
.local-checkbox { display:flex; align-items:center; }.local-checkbox input { width:auto; }
.local-list { padding:0; list-style:none; }.local-list li { display:grid; gap:6px; margin:12px 0; overflow-wrap:anywhere; }
.local-list button { text-align:left; color:var(--ink); border:1px solid var(--line); border-radius:6px; padding:10px; background:var(--panel); }
button { max-width:100%; overflow-wrap:anywhere; }.local-list code { font-size:12px; }
</style>
