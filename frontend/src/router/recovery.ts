import { shallowRef } from 'vue'
import type { Router } from 'vue-router'

export function installNavigationRecovery(router: Router) {
  const failure = shallowRef<{ href: string } | null>(null)
  router.onError((_error, to) => {
    // Keep the current view and its drafts. A native link lets the user fetch the
    // current HTML and chunks, including when this tab predates a service update.
    failure.value = { href: router.resolve(to).href }
  })
  router.afterEach((_to, _from, navigationFailure) => {
    if (!navigationFailure) failure.value = null
  })
  return failure
}
