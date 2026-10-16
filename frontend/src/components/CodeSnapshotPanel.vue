<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { codeSnapshotsApi, type CodeSnapshot, type SnapshotReview } from '@/api/codeSnapshots'

const props = defineProps<{ token: string }>()
const route = useRoute(); const router = useRouter()
const file = ref<File | null>(null); const tool = ref('unknown'); const consent = ref(false)
const review = ref<SnapshotReview | null>(null); const saved = ref<CodeSnapshot | null>(null)
const busy = ref(false); const error = ref(''); let generation = 0; let alive = true
const reasons: Record<string, string> = {
  DEPENDENCY_DIRECTORY: '依赖目录', CACHE_DIRECTORY: '缓存目录', BUILD_OUTPUT: '构建产物',
  GENERATED_ARTIFACT: '生成的产物', BINARY_OR_NON_UTF8: '二进制或非 UTF-8 内容',
  UNSAFE_PATH: '不安全路径', PRIVATE_OR_UNSAFE_NAME: '私密或不安全文件名',
  SYMLINK_OR_SPECIAL_FILE: '符号链接或特殊文件', ENCRYPTED_ENTRY: '加密条目',
  NAME_COLLISION: '重复、大小写、NFC 或文件与目录名称冲突', CREDENTIAL_CONTENT: '内容命中凭据规则',
  NESTED_ARCHIVE: '嵌套归档', CORRUPT_ARCHIVE: '归档损坏或截断', EMPTY_SOURCE_SUBSET: '无可纳入的源码',
  SNAPSHOT_FILE_LIMIT: '最终快照超过 500 个文件', SNAPSHOT_BYTE_LIMIT: '最终快照超过 4,000,000 字节',
  SNAPSHOT_STORAGE_CAPACITY: '私有存储容量不足，未写入快照；请由操作员准备独立存储',
  SNAPSHOT_METADATA_LIMIT: '源码与完整清单的存储编码超过 8,000,000 字节',
  UPLOAD_LIMIT: '上传超过 8,000,000 字节', SCAN_ENTRY_LIMIT: '扫描超过 10,000 个条目',
  SCAN_ENTRY_BYTE_LIMIT: '单条目解压超过 8,000,000 字节', SCAN_BYTE_LIMIT: '扫描解压超过 32,000,000 字节',
  COMPRESSION_RATIO_LIMIT: '压缩比超过 200 倍', DECOMPRESSION_LIMIT: '条目解压大小异常',
  UNSUPPORTED_COMPRESSION: '不支持的压缩方法', DIRECTORY_CONTENT: '目录含异常内容',
}
function reset() { generation++; busy.value = false; review.value = null; consent.value = false; error.value = ''; saved.value = null }
function selectFile(event: Event) { reset(); file.value = (event.target as HTMLInputElement).files?.[0] ?? null }
function report(e: unknown) {
  const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code
  error.value = `操作未完成：${(code?.startsWith('ZIP_') && reasons[code.slice(4)]) || code || 'NETWORK_ERROR'}。未保存新快照，请检查本地操作员权限、归档或重新预检。`
}
async function preview() {
  if (!file.value || !props.token || busy.value) return
  reset(); const current = generation; busy.value = true
  try { const result = await codeSnapshotsApi.preview(file.value, tool.value, props.token); if (alive && current === generation) review.value = result }
  catch (e) {
    if (alive && current === generation) {
      const code = (e as { response?: { data?: { error?: { code?: string } } } }).response?.data?.error?.code
      if (code === 'ZIP_UPLOAD_LIMIT') review.value = { status: 'REJECTED', rejections: [{ reason: 'UPLOAD_LIMIT', entry: null, path: null }] }
      else report(e)
    }
  }
  finally { if (alive && current === generation) busy.value = false }
}
async function confirm() {
  if (!file.value || !consent.value || review.value?.status !== 'REVIEW_REQUIRED' || busy.value) return
  const current = generation; busy.value = true; error.value = ''
  try {
    const result = await codeSnapshotsApi.confirm(file.value, tool.value, review.value, props.token)
    if (!alive || current !== generation) return
    saved.value = result; review.value = null; consent.value = false; file.value = null
    await router.push(`/code-snapshots/${result.identity}`)
  } catch (e) { if (alive && current === generation) { consent.value = false; report(e) } }
  finally { if (alive && current === generation) busy.value = false }
}
async function load() {
  const id = route.params.snapshotIdentity
  if (!id || !props.token) return
  reset(); const current = generation; busy.value = true
  try { const result = await codeSnapshotsApi.detail(String(id), props.token); if (alive && current === generation) saved.value = result }
  catch (e) { if (alive && current === generation) report(e) }
  finally { if (alive && current === generation) busy.value = false }
}
watch(tool, reset)
watch(() => props.token, () => { reset(); void load() })
watch(() => route.params.snapshotIdentity, () => { reset(); void load() }, { immediate: true })
onBeforeUnmount(() => { alive = false; generation++; file.value = null; review.value = null; saved.value = null })
</script>

<template>
  <section class="panel builder-form code-snapshot-panel" data-test="code-snapshot-panel" :aria-busy="busy">
    <h3>保存源码快照 · 从网页选择 ZIP</h3>
    <p>先保存代码，后续再绑定可信任务。仅安全解析，不执行上传内容；工具来源只是声明。</p>
    <p>原始归档上传 ≤ 8,000,000 字节；扫描 ≤ 10,000 条目 / 32,000,000 解压字节，单条目 ≤ 8,000,000 字节、压缩比 ≤ 200；最终源码快照 ≤ 500 文件 / 4,000,000 字节。</p>
    <label>声明的生成工具<select v-model="tool" data-test="snapshot-tool" :disabled="busy"><option value="unknown">未声明</option><option value="deepseek-harness-desktop">DeepSeek Harness Desktop</option><option value="codex">Codex</option><option value="claude-code">Claude Code</option><option value="other">其他工具</option></select></label>
    <label>原始归档<input type="file" accept=".zip,application/zip" data-test="snapshot-file" :disabled="busy" @change="selectFile" /></label>
    <p v-if="file">所选原始归档：{{ file.size.toLocaleString() }} 字节</p>
    <p v-if="!token">请先在本页输入本地操作员凭据。凭据和选择的 ZIP 仅留在页面内存。</p>
    <button class="secondary-button" type="button" data-test="snapshot-preview" :disabled="busy || !file || !token" @click="preview">安全预检 ZIP</button>
    <p v-if="error" role="alert" data-test="snapshot-error">{{ error }}</p>
    <div v-if="review?.status === 'REJECTED'" data-test="snapshot-rejected" role="alert">
      <h4>整包拒绝 · 未保存快照</h4>
      <ul><li v-for="(item, index) in review.rejections" :key="index">{{ item.path ?? (item.entry === null ? '原始归档' : `条目 #${item.entry + 1}`) }}：{{ reasons[item.reason] ?? item.reason }} <code>{{ item.reason }}</code></li></ul>
    </div>
    <div v-if="review?.status === 'REVIEW_REQUIRED'" data-test="snapshot-review">
      <h4>待确认的最终源码快照</h4>
      <p>原始归档：{{ review.manifest.archive_bytes }} 字节 · <code>{{ review.manifest.archive_sha256 }}</code></p>
      <p>纳入 {{ review.manifest.included.length }} 个文件；排除 {{ review.manifest.excluded.length }} 个文件；目录条目 {{ review.manifest.directories.length }} 个。</p>
      <p>最终源码快照仅包含下列纳入文件，不代表完整导入原始 ZIP。</p>
      <details open><summary>纳入清单</summary><ul><li v-for="item in review.manifest.included" :key="item.path">{{ item.path }} · {{ item.bytes }} 字节 · <code>{{ item.sha256 }}</code></li></ul></details>
      <details open><summary>排除清单与原因</summary><ul><li v-for="item in review.manifest.excluded" :key="item.path">{{ item.path }}：{{ reasons[item.reason ?? ''] ?? item.reason }} · <code>{{ item.sha256 }}</code></li></ul><p v-if="!review.manifest.excluded.length">无排除文件</p></details>
      <details><summary>目录条目（不计入源码文件数）</summary><ul><li v-for="name in review.manifest.directories" :key="name">{{ name }}</li></ul></details>
      <label class="snapshot-consent"><input v-model="consent" type="checkbox" data-test="snapshot-consent" :disabled="busy" />我已审阅纳入与排除清单，确认仅保存这个源码子集；来源未认证、无运行记录、未验收。</label>
      <button type="button" class="primary-button" data-test="snapshot-confirm" :disabled="busy || !consent" @click="confirm">确认保存不可变快照</button>
    </div>
    <div v-if="saved" data-test="snapshot-detail">
      <h4>已保存 · 最终源码快照</h4>
      <p><code>{{ saved.source_authenticity }}</code> · <code>{{ saved.run_record }}</code> · <code>{{ saved.verification }}</code></p>
      <p>此快照未绑定任务。后续需要另行审查并绑定可信任务及独立验收条件，获得有效验收收据后才能判断结果。本轮只保存快照。</p>
      <p>原始归档：{{ saved.manifest.archive_bytes }} 字节 · <code>{{ saved.manifest.archive_sha256 }}</code></p>
      <p>最终源码快照：纳入 {{ saved.manifest.included.length }} 文件，排除 {{ saved.manifest.excluded.length }} 文件 · <code>{{ saved.manifest.content_digest }}</code></p>
      <RouterLink :to="`/code-snapshots/${saved.identity}`">快照详情链接</RouterLink>
      <details open><summary>纳入清单与逐文件摘要</summary><ul><li v-for="item in saved.manifest.included" :key="item.path">{{ item.path }} · <code>{{ item.sha256 }}</code></li></ul></details>
      <details open><summary>保留的排除清单</summary><ul><li v-for="item in saved.manifest.excluded" :key="item.path">{{ item.path }}：{{ reasons[item.reason ?? ''] ?? item.reason }} · <code>{{ item.sha256 }}</code></li></ul></details>
      <details><summary>确认记录</summary><p>{{ saved.confirmation.consent }}</p><p>确认清单摘要：<code>{{ saved.confirmation.manifest_sha256 }}</code></p><p>快照身份：<code>{{ saved.identity }}</code></p></details>
    </div>
  </section>
</template>

<style scoped>
.code-snapshot-panel { margin-block: 1rem; }
.code-snapshot-panel code, .code-snapshot-panel li { overflow-wrap: anywhere; }
.snapshot-consent { display: flex; gap: .6rem; align-items: flex-start; }
.snapshot-consent input { width: auto; min-height: 0; margin-top: .25rem; }
</style>
