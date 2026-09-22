import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach } from 'vitest'
enableAutoUnmount(afterEach)
import { vi } from 'vitest'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', { value: ResizeObserverStub })

vi.mock('@/charts/echarts', () => ({
  init: () => ({ setOption: vi.fn(), dispose: vi.fn(), resize: vi.fn() }),
}))

Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true })
