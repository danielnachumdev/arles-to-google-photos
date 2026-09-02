import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetSettingsStore, setSettingsStore } from '../settings.ts'
import { SpyKvStore } from '../../testing/index.ts'
import { messages } from './catalogs.ts'
import {
  APP_DIR,
  APP_LANGUAGE,
  applyDocumentLanguage,
  getAppLanguage,
  getLanguageSnapshot,
  initLanguageFromStorage,
  jobStatusLabel,
  jobTypeLabel,
  setAppLanguage,
  subscribeLanguage,
  t,
} from './store.ts'

describe('language store', () => {
  beforeEach(() => {
    setAppLanguage('he', false)
  })

  afterEach(() => {
    setAppLanguage('he', false)
    resetSettingsStore()
  })

  it('defaults to Hebrew rtl', () => {
    expect(getAppLanguage()).toBe('he')
    expect(APP_LANGUAGE).toBe('he')
    expect(APP_DIR).toBe('rtl')
    expect(t.navSettings).toBe(messages.he.navSettings)
  })

  it('updates catalog, dir, document, and subscribers', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeLanguage(listener)
    const epochBefore = getLanguageSnapshot()

    setAppLanguage('en', false)

    expect(getAppLanguage()).toBe('en')
    expect(APP_LANGUAGE).toBe('en')
    expect(APP_DIR).toBe('ltr')
    expect(t.navSettings).toBe(messages.en.navSettings)
    expect(t).toBe(messages.en)
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.title).toBe(messages.en.documentTitle)
    expect(getLanguageSnapshot()).toBe(epochBefore + 1)
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it('persists language when persist is true', () => {
    const store = new SpyKvStore()
    setSettingsStore(store)

    setAppLanguage('en')

    expect(store.set).toHaveBeenCalledWith('language', 'en')
    expect(getAppLanguage()).toBe('en')
  })

  it('does not persist when persist is false', () => {
    const store = new SpyKvStore()
    setSettingsStore(store)

    setAppLanguage('en', false)

    expect(store.set).not.toHaveBeenCalled()
  })

  it('still writes when setting the same language with persist', () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    const listener = vi.fn()
    const unsubscribe = subscribeLanguage(listener)
    const epochBefore = getLanguageSnapshot()

    setAppLanguage('he')

    expect(store.set).toHaveBeenCalledWith('language', 'he')
    expect(listener).not.toHaveBeenCalled()
    expect(getLanguageSnapshot()).toBe(epochBefore)
    unsubscribe()
  })

  it('loads stored language without rewriting it', () => {
    const store = new SpyKvStore({ language: 'en' })
    setSettingsStore(store)

    initLanguageFromStorage()

    expect(getAppLanguage()).toBe('en')
    expect(APP_DIR).toBe('ltr')
    expect(t.documentTitle).toBe(messages.en.documentTitle)
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(store.set).not.toHaveBeenCalled()
  })

  it('applies document lang, dir, and title from the active catalog', () => {
    setAppLanguage('en', false)
    document.title = 'stale'
    document.documentElement.lang = 'xx'
    document.documentElement.dir = 'rtl'

    applyDocumentLanguage()

    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.title).toBe(messages.en.documentTitle)
  })

  it('translates job status and type labels for the active language', () => {
    expect(jobStatusLabel('pending')).toBe(messages.he.statusPending)
    expect(jobStatusLabel('running')).toBe(messages.he.statusRunning)
    expect(jobStatusLabel('waiting')).toBe(messages.he.statusWaiting)
    expect(jobStatusLabel('done')).toBe(messages.he.statusDone)
    expect(jobStatusLabel('failed')).toBe(messages.he.statusFailed)
    expect(jobStatusLabel('cancelled')).toBe(messages.he.statusCancelled)
    expect(jobStatusLabel('other')).toBe('other')
    expect(jobTypeLabel('preview')).toBe(messages.he.typePreview)
    expect(jobTypeLabel('upload')).toBe(messages.he.typeUpload)
    expect(jobTypeLabel('scrape')).toBe(messages.he.typeScrape)
    expect(jobTypeLabel('other')).toBe('other')

    setAppLanguage('en', false)

    expect(jobStatusLabel('done')).toBe(messages.en.statusDone)
    expect(jobTypeLabel('scrape')).toBe(messages.en.typeScrape)
  })
})
