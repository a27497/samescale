import 'element-plus/es/components/tooltip/style/css'
import './styles.css'

import { ElTooltip } from 'element-plus'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'

createApp(App)
  .use(createPinia())
  .use(router)
  .component('ElTooltip', ElTooltip)
  .mount('#app')
