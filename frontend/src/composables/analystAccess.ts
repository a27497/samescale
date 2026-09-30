import { ref } from 'vue'
import { analystApi } from '@/api/analyst'

export function useAnalystAccess() {
  const access = ref<'loading' | 'public' | 'private' | 'unavailable'>('loading')
  async function loadAccess() {
    access.value = 'loading'
    try {
      const result = await analystApi.capabilities()
      access.value = result.public_demo_read_only ? 'public'
        : result.persistent_sessions_allowed ? 'private' : 'unavailable'
    } catch { access.value = 'unavailable' }
  }
  return { access, loadAccess }
}
