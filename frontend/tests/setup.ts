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

// jsdom has no viewport; browser acceptance verifies real scroll restoration.
Object.defineProperty(window, 'scrollTo', { configurable: true, value: vi.fn() })
