<script setup lang="ts">
import { t } from '@/composables/i18n'
import { inject, onMounted, ref } from 'vue'
import { productModeKey } from '@/composables/productContext'
import { preferences, loadPreferences, savePreferences, resetPreferences } from '@/composables/preferences'


const mode = inject(productModeKey, ref('unknown'))
const saved = ref('')
function save(reset = false) {
  const persisted = reset ? resetPreferences() : savePreferences()
  saved.value = persisted ? (reset ? '已恢复默认显示设置。' : '已保存到当前浏览器。') : '已在当前页面生效；浏览器存储不可用，刷新后可能恢复默认。'
}
onMounted(loadPreferences)
</script>

<template>
  <section class="project-settings">
    <div class="page-heading"><div><h2>{{ t('项目设置') }}</h2><p>{{ t('当前浏览器的显示偏好与工作区入口。') }}</p></div></div>
    <nav class="settings-sections" :aria-label="t('设置分类')">
      <a href="#appearance">{{ t('外观与阅读') }}</a><a href="#workspace">{{ t('工作区与数据') }}</a><RouterLink to="/connections">{{ t('连接与配置') }}</RouterLink>
    </nav>
    <section id="appearance" class="settings-section" aria-labelledby="appearance-title">
      <div class="settings-section-heading"><h3 id="appearance-title">{{ t('外观与阅读') }}</h3><span>{{ t('当前浏览器') }}</span></div>
      <div class="settings-row"><div><label for="text-size">{{ t('文字大小') }}</label><p>{{ t('应用于导航、正文和工具页面。内容与证据数据保持原样。') }}</p></div><select id="text-size" v-model="preferences.textSize" @change="save()"><option value="standard">{{ t('标准 · 15px 正文') }}</option><option value="large">{{ t('较大 · 16px 正文') }}</option></select></div>
      <div class="settings-row"><div><label for="reduce-motion">{{ t('减少界面动效') }}</label><p>{{ t('减少侧栏过渡与滚动动画。') }}</p></div><input id="reduce-motion" v-model="preferences.reduceMotion" type="checkbox" @change="save()" /></div>
      <div class="settings-row"><div><label for="interface-language">{{ t('界面语言') }}</label><p>{{ t('切换导航、设置与工具界面的语言。原始证据与技术标识保留原文。') }}</p></div><select id="interface-language" v-model="preferences.language" @change="save()"><option value="zh-CN">{{ t('简体中文') }}</option><option value="en">English</option></select></div>
      <div class="settings-row"><div><strong>{{ t('界面主题') }}</strong><p>{{ t('冷灰与白色') }}</p></div><button class="secondary-button" @click="save(true)">{{ t('恢复默认显示') }}</button></div>
      <p v-if="saved" role="status" class="settings-feedback">{{ t(saved) }}</p>
    </section>
    <section id="workspace" class="settings-section" aria-labelledby="workspace-title">
      <div class="settings-section-heading"><h3 id="workspace-title">{{ t('工作区与数据') }}</h3><span>{{ t('本地项目') }}</span></div>
      <div class="settings-row"><div><strong>{{ t('离线案例') }}</strong><p>{{ t('无需密钥、数据库或 Docker；使用合成证据，无模型调用、不保存结果。') }}</p></div><RouterLink class="table-link" to="/analyst?example=offline">{{ t('打开 Sample') }}</RouterLink></div>
      <div v-if="mode === 'workspace'" class="settings-row"><div><strong>{{ t('已保存调查') }}</strong><p>{{ t('由本地 PostgreSQL 保存进度与方案审阅状态，需要完整服务及已有实验证据。') }}</p></div><RouterLink class="table-link" to="/analyst/sessions">{{ t('查看调查') }}</RouterLink></div>
      <div class="settings-row"><div><strong>{{ t('历史真实记录') }}</strong><p>{{ t('只读查看冻结报告；不会恢复原会话，也不会发起模型调用。') }}</p></div><RouterLink class="table-link" to="/analyst?example=historical">{{ t('查看历史记录') }}</RouterLink></div>
    </section>
    <section id="connections" class="settings-section" aria-labelledby="connections-title">
      <div class="settings-section-heading"><h3 id="connections-title">{{ t('连接与配置') }}</h3><span>{{ t('服务端只读') }}</span></div>
      <div class="settings-row"><div><strong>{{ t('模型、服务与运行配置') }}</strong><p>{{ t('查看凭据、连接健康、组合兼容和执行授权。') }}</p></div><RouterLink class="table-link" to="/connections">{{ t('连接总览') }}</RouterLink></div>
      <div id="runtime" class="settings-row"><div><strong>{{ t('运行默认值') }}</strong><p>{{ t('当前网页不编辑 API Key 或服务端配置。') }}</p></div><RouterLink class="table-link" to="/connections#runtime">{{ t('查看默认值') }}</RouterLink></div>
    </section>
    <footer class="settings-about"><strong>SameScale</strong><p>{{ t('比较模型与 Agent 的任务表现，沿可核对的证据分析差异。结论范围以实际证据为准。') }}</p></footer>
  </section>
</template>
