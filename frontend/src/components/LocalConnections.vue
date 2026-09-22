<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { localConfigurationApi as api, type ConnectionMetadata, type CredentialMetadata } from '@/api/localConfiguration'
import type { ProviderDefinition } from '@/types/registry'
import { t } from '@/composables/i18n'

const props = defineProps<{ token: string; providers: ProviderDefinition[] }>()
const emit = defineEmits<{ updated: [connections: ConnectionMetadata[]]; changed: [] }>()
const credentials = ref<CredentialMetadata[]>([]); const connections = ref<ConnectionMetadata[]>([])
const busy = ref(false); const error = ref(''); const message = ref('')
const key = reactive({ id: '', name: '', value: '', enabled: true, revision: 0 })
const connection = reactive({ id: '', name: '', provider: '', protocol: 'responses', url: '', credential: '', enabled: true, revision: 0 })
const providers = computed(() => props.providers.filter(p => !p.provider_id.startsWith('local-connection-')))
const provider = computed(() => providers.value.find(p => p.provider_id === connection.provider))
const protocols = computed(() => provider.value?.protocols.filter(p => ['responses', 'chat_completions', 'messages'].includes(p)) ?? [])
const idValid = (id: string) => /^[a-z][a-z0-9-]{0,31}$/.test(id)
const keyValid = computed(() => idValid(key.id) && key.name.trim() && (key.revision > 0 || key.value.length > 0))
const connectionValid = computed(() => idValid(connection.id) && connection.name.trim() && provider.value && protocols.value.includes(connection.protocol)
  && (connection.revision > 0 || connection.url.length > 0) && (!connection.credential || credentials.value.some(c => c.credential_id === connection.credential)))
let generation = 0
function clearKey() { Object.assign(key, { id: '', name: '', value: '', enabled: true, revision: 0 }) }
function clearConnection() { Object.assign(connection, { id: '', name: '', provider: providers.value[0]?.provider_id ?? '', protocol: providers.value[0]?.protocols[0] ?? '', url: '', credential: '', enabled: true, revision: 0 }) }
function editKey(item: CredentialMetadata) { Object.assign(key, { id: item.credential_id, name: item.name, value: '', enabled: item.enabled, revision: item.revision }); message.value = '' }
function editConnection(item: ConnectionMetadata) { Object.assign(connection, { id: item.connection_id, name: item.name, provider: item.template_provider_id, protocol: item.protocol, url: '', credential: item.credential_id ?? '', enabled: item.enabled, revision: item.revision }); message.value = '' }
async function load() {
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''; credentials.value = []; connections.value = []; emit('updated', [])
  key.value = ''; connection.url = ''
  try {
    const [keys, services] = await Promise.all([api.credentials(props.token), api.connections(props.token)])
    if (current !== generation) return false
    credentials.value = keys.items; connections.value = services.items; emit('updated', services.items); clearKey(); clearConnection(); return true
  } catch { if (current === generation) error.value = '连接与凭据读取失败，请重新读取。'; return false }
  finally { if (current === generation) busy.value = false }
}
async function saveKey() {
  if (busy.value || !keyValid.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  const payload = { name: key.name.trim(), expected_revision: key.revision, enabled: key.enabled, ...(key.value ? { value: key.value } : {}) }
  key.value = ''
  try {
    await api.saveCredential(key.id, payload, props.token)
    if (current !== generation) return
    emit('changed'); if (await load()) message.value = '凭据已保存。关联连接需重新保存以绑定当前版本。'
  } catch { if (current === generation) error.value = '保存未确认。请重新读取，并检查凭据目录或版本冲突。' }
  finally { if (current === generation) busy.value = false }
}
async function saveConnection() {
  if (busy.value || !connectionValid.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  const selected = credentials.value.find(c => c.credential_id === connection.credential)
  const payload = { name: connection.name.trim(), expected_revision: connection.revision, enabled: connection.enabled, template_provider_id: connection.provider, protocol: connection.protocol,
    ...(connection.url ? { base_url: connection.url } : {}), credential_id: selected?.credential_id ?? null, credential_revision: selected?.revision ?? null, environment_reference: selected ? null : provider.value!.credential_ref }
  connection.url = ''
  try {
    await api.saveConnection(connection.id, payload, props.token)
    if (current !== generation) return
    emit('changed'); if (await load()) message.value = '连接已保存。请重新保存关联模型配置以绑定当前版本。'
  } catch { if (current === generation) error.value = '保存未确认。请重新读取，并检查凭据目录或版本冲突。' }
  finally { if (current === generation) busy.value = false }
}
async function check(item: ConnectionMetadata) {
  if (busy.value) return
  const current = ++generation; busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api.checkConnection(item.connection_id, props.token)
    if (current === generation) message.value = result.connection.ready_for_planning ? '本地引用可用；未联网，连接健康与密钥有效性仍未验证。' : '本地配置不可用，请检查启停状态、引用版本及凭据目录。'
  } catch { if (current === generation) error.value = '配置校验失败，请重新读取。' }
  finally { if (current === generation) busy.value = false }
}
onMounted(load); onBeforeUnmount(() => { generation++; key.value = ''; connection.url = '' })
</script>

<template>
  <section class="local-connections" aria-labelledby="local-connections-title">
    <h4 id="local-connections-title">{{ t('服务连接与凭据') }}</h4>
    <p>{{ t('保存不会联网或执行评测。密钥与地址不回显；留空保留已存值，输入新值即替换。') }}</p>
    <button class="secondary-button" :disabled="busy" @click="load">{{ t('重新读取连接与凭据') }}</button>
    <p v-if="error" class="error-state" role="alert">{{ t(error) }}</p><p v-if="message" role="status">{{ t(message) }}</p>
    <div class="management-grid">
      <section class="credential-editor">
        <h5>{{ t('凭据') }}</h5><button class="secondary-button" :disabled="busy" @click="clearKey">{{ t('新增凭据') }}</button>
        <ul><li v-for="item in credentials" :key="item.credential_id"><button :disabled="busy" @click="editKey(item)">{{ item.name }} · v{{ item.revision }} · {{ t(item.enabled ? (item.present ? '已配置' : '不可用') : '已停用') }}</button><code>{{ item.reference }}</code></li></ul>
        <form @submit.prevent="saveKey"><fieldset :disabled="busy"><legend>{{ t('保存或轮换凭据') }}</legend>
          <label>{{ t('凭据 ID') }}<input v-model="key.id" :disabled="key.revision > 0" maxlength="32" pattern="[a-z][a-z0-9\-]{0,31}" required></label>
          <label>{{ t('凭据名称') }}<input v-model="key.name" maxlength="100" required></label>
          <label>{{ t('新的 API Key') }}<input v-model="key.value" type="password" autocomplete="off" maxlength="8192" :required="key.revision === 0"></label>
          <label class="check-row"><input v-model="key.enabled" type="checkbox">{{ t('启用凭据') }}</label>
          <button class="primary-button" :disabled="!keyValid">{{ t('保存凭据') }}</button>
        </fieldset></form>
      </section>
      <section class="connection-editor">
        <h5>{{ t('服务连接') }}</h5><button class="secondary-button" :disabled="busy" @click="clearConnection">{{ t('新增连接') }}</button>
        <ul><li v-for="item in connections" :key="item.connection_id"><button :disabled="busy" @click="editConnection(item)">{{ item.name }} · v{{ item.revision }} · {{ t(item.enabled ? (item.ready_for_planning ? '本地引用可用' : '需要检查引用') : '已停用') }}</button><span>{{ t('连接健康：未验证') }}</span><button class="secondary-button" :disabled="busy" @click="check(item)">{{ t('校验配置（不联网）') }}</button></li></ul>
        <form @submit.prevent="saveConnection"><fieldset :disabled="busy"><legend>{{ t('保存服务连接') }}</legend>
          <label>{{ t('连接 ID') }}<input v-model="connection.id" :disabled="connection.revision > 0" maxlength="32" pattern="[a-z][a-z0-9\-]{0,31}" required></label>
          <label>{{ t('连接名称') }}<input v-model="connection.name" maxlength="100" required></label>
          <label>{{ t('服务商模板') }}<select v-model="connection.provider" :aria-label="t('服务商模板')" @change="connection.protocol = protocols[0] ?? ''"><option v-for="p in providers" :key="p.provider_id" :value="p.provider_id">{{ p.display_name }}</option></select></label>
          <label>{{ t('协议') }}<select v-model="connection.protocol" :aria-label="t('协议')"><option v-for="protocol in protocols" :key="protocol" :value="protocol">{{ protocol }}</option></select></label>
          <label>{{ t('新的服务地址') }}<input v-model="connection.url" type="url" autocomplete="off" placeholder="https://provider.example/v1" maxlength="500" :required="connection.revision === 0"></label>
          <label>{{ t('凭据来源') }}<select v-model="connection.credential" :aria-label="t('凭据来源')"><option value="">{{ t('沿用模板环境变量') }} · {{ provider?.credential_ref }}</option><option v-for="item in credentials" :key="item.credential_id" :value="item.credential_id">{{ item.name }} · v{{ item.revision }} · {{ t(item.enabled ? '已启用' : '已停用') }}</option></select></label>
          <label class="check-row"><input v-model="connection.enabled" type="checkbox">{{ t('启用连接') }}</label>
          <button class="primary-button" :disabled="!connectionValid">{{ t('保存连接') }}</button>
        </fieldset></form>
      </section>
    </div>
  </section>
</template>

<style scoped>
.local-connections { border:1px solid var(--line); padding:16px; border-radius:8px; margin:16px 0 24px; }
.management-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; }.management-grid > section { min-width:0; }
p, li span { font:var(--type-caption); color:var(--muted); }ul { padding:0; list-style:none; }li { display:grid; gap:8px; margin:12px 0; overflow-wrap:anywhere; }
fieldset, label { display:grid; gap:8px; min-width:0; }fieldset { border:1px solid var(--line); border-radius:6px; padding:12px; gap:16px; }
input,select { box-sizing:border-box; width:100%; min-width:0; padding:10px; border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--ink); font:var(--type-control); }
button { max-width:100%; overflow-wrap:anywhere; }li > button:first-child { text-align:left; padding:10px; border:1px solid var(--line); border-radius:6px; color:var(--ink); background:var(--panel); }
code { font-size:12px; overflow-wrap:anywhere; }.check-row { display:flex; align-items:center; }.check-row input { width:auto; }
@media(max-width:760px) { .management-grid { grid-template-columns:1fr; } }
</style>
