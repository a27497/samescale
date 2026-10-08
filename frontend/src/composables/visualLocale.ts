import { watch } from 'vue'
import { preferences } from './preferences'

export type VisualLocale = 'zh-CN' | 'en-US'
// Only interface copy goes through this function. API evidence stays verbatim.
export function copy(zh: string, en: string): string {
  return preferences.language === 'en' || preferences.language === 'en-US' ? en : zh
}
export function setLocale(locale: VisualLocale) {
  preferences.language = locale
  try { localStorage.setItem('samescale.interface-locale', locale) } catch { /* Storage may be disabled. */ }
}
export function initializeLocale() {
  try {
    const saved = localStorage.getItem('samescale.interface-locale')
    if (saved === 'zh-CN' || saved === 'en-US') preferences.language = saved
  } catch { /* Chinese remains the default. */ }
  watch(() => preferences.language, language => {
    document.documentElement.lang = language === 'en' || language === 'en-US' ? 'en-US' : 'zh-CN'
  }, { immediate: true })
}
