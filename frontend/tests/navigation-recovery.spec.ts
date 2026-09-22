import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App.vue'
import router, { navigationFailure } from '@/router'

vi.mock('@/components/ProductStatus.vue', () => ({ default: { template: '<div />' } }))

describe('navigation recovery', () => {
  beforeEach(async () => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    router.addRoute({ path: '/test-draft', component: { template: '<textarea aria-label="draft" />' } })
    router.addRoute({ path: '/test-destination', component: { template: '<p>Loaded</p>' } })
    router.addRoute({ path: '/test-missing', component: () => Promise.reject(new TypeError('Failed to fetch dynamically imported module')) })
    await router.push('/test-draft')
  })

  it('preserves the view and draft, closes mobile navigation, and offers a focused native reload link', async () => {
    const wrapper = mount(App, { attachTo: document.body, global: { plugins: [router] } })
    await wrapper.get('textarea').setValue('unsaved investigation')
    await wrapper.get('.mobile-menu-button').trigger('click')
    await expect(router.push('/test-missing?case=abc#evidence')).rejects.toThrow('Failed to fetch')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/test-draft')
    expect(wrapper.get('textarea').element.value).toBe('unsaved investigation')
    expect(wrapper.find('.nav-scrim').exists()).toBe(false)
    const notice = wrapper.get('[role="alert"]')
    expect(notice.text()).toContain('页面加载失败')
    expect(notice.get('a').attributes('href')).toBe('/test-missing?case=abc#evidence')
    expect(document.activeElement).toBe(notice.element)
  })

  it('clears the notice after a successful navigation', async () => {
    await expect(router.push('/test-missing')).rejects.toThrow()
    expect(navigationFailure.value).not.toBeNull()
    await router.push('/test-destination')
    expect(navigationFailure.value).toBeNull()
  })

  it('renders a recovery link even when the initial navigation failed before mounting', async () => {
    await expect(router.push('/test-missing')).rejects.toThrow()
    const wrapper = mount(App, { global: { plugins: [router] } })
    expect(wrapper.get('[role="alert"] a').attributes('href')).toBe('/test-missing')
  })
})
