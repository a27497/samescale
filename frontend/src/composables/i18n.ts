import { preferences } from './preferences'
import english from './en.json'

const messages: Record<string, string> = english
// Translate interface messages only; callers preserve evidence and registry values verbatim.
export function t<T>(message: T): T | string {
  if (typeof message !== 'string' || preferences.language !== 'en') return message
  return messages[message] ?? message
}
