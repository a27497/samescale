import { computed, onBeforeUnmount, ref } from 'vue'

const storageKey = 'samescale.sidebar.width.v1'
const minimum = 200
const maximum = 420
const defaultWidth = 248

export function useSidebarResize() {
  const preferredWidth = ref(defaultWidth)
  try {
    const saved = Number(localStorage.getItem(storageKey))
    if (Number.isFinite(saved) && saved >= minimum && saved <= maximum) preferredWidth.value = saved
  } catch { /* The sidebar also works when browser storage is unavailable. */ }
  const viewport = ref(window.innerWidth)
  const maxWidth = computed(() => Math.min(maximum, Math.max(minimum, viewport.value - 480)))
  const width = computed(() => Math.min(preferredWidth.value, maxWidth.value))
  const resizing = ref(false)
  let drag: { id: number; x: number; width: number; preferred: number; handle: HTMLElement } | null = null
  const clamp = (value: number) => Math.round(Math.min(maxWidth.value, Math.max(minimum, value)))
  function save() {
    try { localStorage.setItem(storageKey, String(preferredWidth.value)) } catch { /* Session-only sizing. */ }
  }
  function finish(cancel = false) {
    if (!drag) return
    const current = drag
    drag = null
    resizing.value = false
    if (cancel) preferredWidth.value = current.preferred
    else save()
    if (current.handle.hasPointerCapture(current.id)) current.handle.releasePointerCapture(current.id)
  }
  function start(event: PointerEvent) {
    if (event.button !== 0 || !event.isPrimary || viewport.value <= 860) return
    const handle = event.currentTarget as HTMLElement
    handle.setPointerCapture(event.pointerId)
    handle.focus()
    drag = { id: event.pointerId, x: event.clientX, width: width.value, preferred: preferredWidth.value, handle }
    resizing.value = true
    event.preventDefault()
  }
  function move(event: PointerEvent) {
    if (drag?.id === event.pointerId) preferredWidth.value = clamp(drag.width + event.clientX - drag.x)
  }
  function end(event: PointerEvent) {
    if (drag?.id === event.pointerId) finish(event.type === 'pointercancel')
  }
  function reset() { finish(true); preferredWidth.value = defaultWidth; save() }
  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape') { finish(true); return }
    const values: Record<string, number> = { ArrowLeft: width.value - 16, ArrowRight: width.value + 16, Home: minimum, End: maxWidth.value }
    const value = values[event.key]
    if (value === undefined) return
    event.preventDefault()
    preferredWidth.value = clamp(value)
    save()
  }
  function onResize() { finish(true); viewport.value = window.innerWidth }
  window.addEventListener('resize', onResize)
  onBeforeUnmount(() => { finish(true); window.removeEventListener('resize', onResize) })
  return { width, minimum, maxWidth, resizing, start, move, end, reset, keydown }
}
