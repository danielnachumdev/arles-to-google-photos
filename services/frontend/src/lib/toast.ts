export const TOAST_TYPES = ['good', 'bad', 'warning', 'regular'] as const

export type ToastType = (typeof TOAST_TYPES)[number]

export type ToastRecord = {
  id: string
  type: ToastType
  message: string
  durationMs: number
  href?: string
  linkLabel?: string
}

export type ToastContentOptions = {
  message: string
  durationMs?: number
  href?: string
  linkLabel?: string
}

export type ToastShowOptions = ToastContentOptions & {
  type?: ToastType
}

export const TOAST_DURATION_MS: Record<ToastType, number> = {
  good: 3500,
  regular: 4000,
  warning: 6500,
  bad: 8000,
}

const MAX_TOASTS = 5

const listeners = new Set<() => void>()
const timers = new Map<string, ReturnType<typeof setTimeout>>()

let toasts: ToastRecord[] = []
let nextSeq = 1

function emit(): void {
  listeners.forEach((listener) => listener())
}

function clearTimer(id: string): void {
  const timer = timers.get(id)
  if (timer === undefined) {
    return
  }
  clearTimeout(timer)
  timers.delete(id)
}

export function subscribeToasts(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  return () => {
    listeners.delete(onStoreChange)
  }
}

export function getToasts(): ToastRecord[] {
  return toasts
}

function enqueue(
  type: ToastType,
  message: string,
  extra?: { durationMs?: number; href?: string; linkLabel?: string },
): string {
  const id = `toast-${nextSeq}`
  nextSeq += 1
  const durationMs = extra?.durationMs ?? TOAST_DURATION_MS[type]
  const record: ToastRecord = { id, type, message, durationMs }
  if (extra?.href) {
    record.href = extra.href
  }
  if (extra?.linkLabel) {
    record.linkLabel = extra.linkLabel
  }
  let next = [...toasts, record]
  if (next.length > MAX_TOASTS) {
    const dropped = next.slice(0, next.length - MAX_TOASTS)
    dropped.forEach((item) => clearTimer(item.id))
    next = next.slice(-MAX_TOASTS)
  }
  toasts = next
  emit()

  if (durationMs > 0) {
    timers.set(
      id,
      setTimeout(() => {
        timers.delete(id)
        dismiss(id)
      }, durationMs),
    )
  }
  return id
}

function dismiss(id: string): void {
  clearTimer(id)
  const next = toasts.filter((item) => item.id !== id)
  if (next.length === toasts.length) {
    return
  }
  toasts = next
  emit()
}

function clear(): void {
  timers.forEach((timer) => clearTimeout(timer))
  timers.clear()
  if (toasts.length === 0) {
    return
  }
  toasts = []
  emit()
}

function extrasFromContent(content: ToastContentOptions): {
  durationMs?: number
  href?: string
  linkLabel?: string
} {
  return {
    durationMs: content.durationMs,
    href: content.href,
    linkLabel: content.linkLabel,
  }
}

function show(message: string, type?: ToastType): string
function show(options: ToastShowOptions): string
function show(messageOrOptions: string | ToastShowOptions, type: ToastType = 'regular'): string {
  if (typeof messageOrOptions === 'string') {
    return enqueue(type, messageOrOptions)
  }
  return enqueue(
    messageOrOptions.type ?? 'regular',
    messageOrOptions.message,
    extrasFromContent(messageOrOptions),
  )
}

function typedToast(type: ToastType, messageOrOptions: string | ToastContentOptions, durationMs?: number): string {
  if (typeof messageOrOptions === 'string') {
    return enqueue(type, messageOrOptions, { durationMs })
  }
  return enqueue(type, messageOrOptions.message, {
    durationMs: messageOrOptions.durationMs ?? durationMs,
    href: messageOrOptions.href,
    linkLabel: messageOrOptions.linkLabel,
  })
}

function good(message: string, durationMs?: number): string
function good(options: ToastContentOptions): string
function good(messageOrOptions: string | ToastContentOptions, durationMs?: number): string {
  return typedToast('good', messageOrOptions, durationMs)
}

function bad(message: string, durationMs?: number): string
function bad(options: ToastContentOptions): string
function bad(messageOrOptions: string | ToastContentOptions, durationMs?: number): string {
  return typedToast('bad', messageOrOptions, durationMs)
}

function warning(message: string, durationMs?: number): string
function warning(options: ToastContentOptions): string
function warning(messageOrOptions: string | ToastContentOptions, durationMs?: number): string {
  return typedToast('warning', messageOrOptions, durationMs)
}

function regular(message: string, durationMs?: number): string
function regular(options: ToastContentOptions): string
function regular(messageOrOptions: string | ToastContentOptions, durationMs?: number): string {
  return typedToast('regular', messageOrOptions, durationMs)
}

export const toast = {
  show,
  good,
  bad,
  warning,
  regular,
  dismiss,
  clear,
}
