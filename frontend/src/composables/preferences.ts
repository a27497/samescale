import { reactive } from 'vue'

const defaults = { textSize: 'standard', reduceMotion: false, language: 'zh-CN' }
const key = 'samescale.ui.preferences.v1'
export const preferences = reactive({ ...defaults })
export function loadPreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? '{}')
    preferences.textSize = ['standard', 'large'].includes(saved.textSize) ? saved.textSize : defaults.textSize
    preferences.reduceMotion = saved.reduceMotion === true
    preferences.language = saved.language === 'en' ? 'en' : 'zh-CN'
  } catch { Object.assign(preferences, defaults) }
  applyPreferences()
}
export function applyPreferences() {
  document.documentElement.lang = preferences.language
  document.documentElement.dataset.textSize = preferences.textSize
  document.documentElement.dataset.reduceMotion = String(preferences.reduceMotion)
}
export function savePreferences(): boolean {
  applyPreferences()
  try { localStorage.setItem(key, JSON.stringify(preferences)); return true } catch { return false }
}
export function resetPreferences(): boolean {
  Object.assign(preferences, defaults)
  return savePreferences()
}
