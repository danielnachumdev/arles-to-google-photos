import '@testing-library/jest-dom/vitest'
import { act, render, renderHook, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { resetSettingsStore, setSettingsStore } from '../settings.ts'
import { SpyKvStore } from '../../testing/index.ts'
import { messages } from './catalogs.ts'
import { setAppLanguage } from './store.ts'
import { useLanguage } from './useLanguage.ts'

function Probe() {
  const { language, dir, t } = useLanguage()
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="dir">{dir}</span>
      <span data-testid="nav">{t.navSettings}</span>
    </div>
  )
}

describe('useLanguage', () => {
  beforeEach(() => {
    setAppLanguage('he', false)
  })

  afterEach(() => {
    setAppLanguage('he', false)
    resetSettingsStore()
  })

  it('returns the active language, dir, and catalog', () => {
    const { result } = renderHook(() => useLanguage())

    expect(result.current.language).toBe('he')
    expect(result.current.dir).toBe('rtl')
    expect(result.current.t.navSettings).toBe(messages.he.navSettings)
  })

  it('re-renders when language changes', () => {
    const { result } = renderHook(() => useLanguage())

    act(() => {
      result.current.setLanguage('en', false)
    })

    expect(result.current.language).toBe('en')
    expect(result.current.dir).toBe('ltr')
    expect(result.current.t).toBe(messages.en)
    expect(result.current.t.navSettings).toBe(messages.en.navSettings)
  })

  it('keeps multiple hook consumers in sync', () => {
    const first = renderHook(() => useLanguage())
    const second = renderHook(() => useLanguage())

    act(() => {
      first.result.current.setLanguage('en', false)
    })

    expect(second.result.current.language).toBe('en')
    expect(second.result.current.t.documentTitle).toBe(messages.en.documentTitle)
  })

  it('re-renders a mounted component when the store changes', () => {
    render(<Probe />)
    expect(screen.getByTestId('language')).toHaveTextContent('he')
    expect(screen.getByTestId('dir')).toHaveTextContent('rtl')
    expect(screen.getByTestId('nav')).toHaveTextContent(messages.he.navSettings)

    act(() => {
      setAppLanguage('en', false)
    })

    expect(screen.getByTestId('language')).toHaveTextContent('en')
    expect(screen.getByTestId('dir')).toHaveTextContent('ltr')
    expect(screen.getByTestId('nav')).toHaveTextContent(messages.en.navSettings)
  })

  it('persists through setLanguage by default', () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    const { result } = renderHook(() => useLanguage())

    act(() => {
      result.current.setLanguage('en')
    })

    expect(store.set).toHaveBeenCalledWith('language', 'en')
    expect(result.current.language).toBe('en')
  })
})
