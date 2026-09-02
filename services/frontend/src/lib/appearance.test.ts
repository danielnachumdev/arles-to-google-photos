import { afterEach, describe, expect, it } from 'vitest'
import { SpyKvStore } from '../testing/index.ts'
import {
  APP_COLOR_SCHEME,
  applyDocumentColorScheme,
  getColorScheme,
  initAppearanceFromStorage,
  setColorScheme,
} from './appearance.ts'
import { resetSettingsStore, setSettingsStore } from './settings.ts'

describe('appearance', () => {
  afterEach(() => {
    setColorScheme('light', false)
    resetSettingsStore()
    delete document.documentElement.dataset.colorScheme
  })

  it('applies the color scheme on the document root', () => {
    applyDocumentColorScheme()
    expect(document.documentElement.dataset.colorScheme).toBe(APP_COLOR_SCHEME)

    setColorScheme('dark', false)
    expect(getColorScheme()).toBe('dark')
    expect(document.documentElement.dataset.colorScheme).toBe('dark')
  })

  it('persists when asked and boots from storage', () => {
    const store = new SpyKvStore({ colorScheme: 'dark' })
    setSettingsStore(store)
    initAppearanceFromStorage()

    expect(getColorScheme()).toBe('dark')
    expect(document.documentElement.dataset.colorScheme).toBe('dark')

    setColorScheme('light')
    expect(store.set).toHaveBeenCalledWith('colorScheme', 'light')
    expect(getColorScheme()).toBe('light')
  })
})
