import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getToasts, subscribeToasts, toast, TOAST_DURATION_MS, TOAST_TYPES } from './toast.ts'

describe('toast store', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    toast.clear()
  })

  afterEach(() => {
    toast.clear()
    vi.useRealTimers()
  })

  it('shows good/bad/warning/regular messages', () => {
    toast.good('נשמר.')
    toast.bad('הפרסום נכשל')
    toast.warning('חסר תיאור')
    toast.regular('מתחברים…')

    expect(getToasts().map((item) => ({ type: item.type, message: item.message }))).toEqual([
      { type: 'good', message: 'נשמר.' },
      { type: 'bad', message: 'הפרסום נכשל' },
      { type: 'warning', message: 'חסר תיאור' },
      { type: 'regular', message: 'מתחברים…' },
    ])
    expect(TOAST_TYPES).toEqual(['good', 'bad', 'warning', 'regular'])
  })

  it('accepts toast.show with a type option', () => {
    const id = toast.show({ type: 'good', message: 'Saved.' })
    expect(id).toMatch(/^toast-\d+$/)
    expect(getToasts()).toEqual([
      { id, type: 'good', message: 'Saved.', durationMs: TOAST_DURATION_MS.good },
    ])
  })

  it('stores an optional router link without embedding HTML in the message', () => {
    const id = toast.regular({
      message: 'ההרצה התחילה.',
      href: '/jobs/job-42',
      linkLabel: 'פתח הרצה',
    })
    expect(getToasts()).toEqual([
      {
        id,
        type: 'regular',
        message: 'ההרצה התחילה.',
        href: '/jobs/job-42',
        linkLabel: 'פתח הרצה',
        durationMs: TOAST_DURATION_MS.regular,
      },
    ])
    expect(getToasts()[0]!.message).not.toMatch(/<a /)
  })

  it('stores multiple toast actions including external album links', () => {
    const id = toast.good({
      message: 'Upload finished.',
      actions: [
        { href: 'https://photos.example/a', label: 'View album', external: true },
        { href: '/jobs/u1', label: 'Open run' },
      ],
    })
    expect(getToasts()).toEqual([
      {
        id,
        type: 'good',
        message: 'Upload finished.',
        actions: [
          { href: 'https://photos.example/a', label: 'View album', external: true },
          { href: '/jobs/u1', label: 'Open run' },
        ],
        durationMs: TOAST_DURATION_MS.good,
      },
    ])
  })

  it('accepts a link on toast.show and typed helpers', () => {
    toast.show({
      type: 'good',
      message: 'Preview is ready.',
      href: '/jobs/preview-1',
      linkLabel: 'Open run',
    })
    toast.bad({
      message: 'Upload failed. boom',
      href: '/jobs/upload-1',
      linkLabel: 'Open run',
    })
    expect(getToasts().map((item) => ({
      type: item.type,
      href: item.href,
      linkLabel: item.linkLabel,
    }))).toEqual([
      { type: 'good', href: '/jobs/preview-1', linkLabel: 'Open run' },
      { type: 'bad', href: '/jobs/upload-1', linkLabel: 'Open run' },
    ])
  })

  it('defaults toast.show(string) to regular', () => {
    toast.show('Working…')
    expect(getToasts()[0]).toMatchObject({ type: 'regular', message: 'Working…' })
  })

  it('dismisses a single toast by id', () => {
    const keep = toast.good('keep')
    const gone = toast.bad('gone')
    toast.dismiss(gone)
    expect(getToasts().map((item) => item.id)).toEqual([keep])
  })

  it('clears the whole stack', () => {
    toast.good('a')
    toast.bad('b')
    toast.clear()
    expect(getToasts()).toEqual([])
  })

  it('auto-dismisses good sooner than bad', () => {
    toast.good('ok')
    toast.bad('fail')
    vi.advanceTimersByTime(TOAST_DURATION_MS.good)
    expect(getToasts().map((item) => item.type)).toEqual(['bad'])
    vi.advanceTimersByTime(TOAST_DURATION_MS.bad - TOAST_DURATION_MS.good)
    expect(getToasts()).toEqual([])
  })

  it('honors durationMs and keeps duration 0 until dismiss', () => {
    toast.warning('soon', 100)
    const sticky = toast.bad('stay', 0)
    vi.advanceTimersByTime(99)
    expect(getToasts()).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(getToasts().map((item) => item.id)).toEqual([sticky])
    vi.advanceTimersByTime(60_000)
    expect(getToasts()).toHaveLength(1)
    toast.dismiss(sticky)
    expect(getToasts()).toEqual([])
  })

  it('stores the duration actually used on each record', () => {
    toast.good('ok')
    toast.bad('stay', 0)
    toast.warning('soon', 100)
    toast.regular({ message: 'custom', durationMs: 2500 })
    expect(getToasts().map((item) => item.durationMs)).toEqual([
      TOAST_DURATION_MS.good,
      0,
      100,
      2500,
    ])
  })

  it('drops the oldest toast when the stack is full', () => {
    const first = toast.regular('1')
    toast.regular('2')
    toast.regular('3')
    toast.regular('4')
    toast.regular('5')
    toast.regular('6')
    expect(getToasts().map((item) => item.message)).toEqual(['2', '3', '4', '5', '6'])
    expect(getToasts().some((item) => item.id === first)).toBe(false)
  })

  it('notifies subscribers on show and dismiss', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeToasts(listener)
    toast.good('ping')
    expect(listener).toHaveBeenCalledTimes(1)
    toast.clear()
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
    toast.regular('nope')
    expect(listener).toHaveBeenCalledTimes(2)
  })
})
