import { reactive } from 'vue'
const defaults = { textSize: 'standard', reduceMotion: false, language: 'zh-CN' }
export const preferences = reactive({ ...defaults })
