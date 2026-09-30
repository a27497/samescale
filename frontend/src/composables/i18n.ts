import { inject, provide, type InjectionKey } from 'vue'
import { preferences } from './preferences'
import english from './en.json'

const messages: Record<string, string> = english
// Translate interface messages only; callers preserve evidence and registry values verbatim.
export function t<T>(message: T): T | string {
  if (typeof message !== 'string' || preferences.language !== 'en') return message
  return messages[message] ?? message
}

const interfaceLanguage: InjectionKey<string> = Symbol('interfaceLanguage')
// Advanced Connections uses English like the surrounding Registry pages.
export function useTranslation(language?: string) {
  const inherited = inject(interfaceLanguage, undefined)
  if (language) provide(interfaceLanguage, language)
  return <T>(message: T): T | string => {
    if ((language ?? inherited) === 'en' && typeof message === 'string') return messages[message] ?? message
    return t(message)
  }
}
