import 'element-plus/es/components/tooltip/style/css'
import './styles.css'

import { ElTooltip } from 'element-plus'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { loadPreferences } from './composables/preferences'
import router from './router'

loadPreferences()

createApp(App)
  .use(createPinia())
  .use(router)
  .component('ElTooltip', ElTooltip)
  .mount('#app')
