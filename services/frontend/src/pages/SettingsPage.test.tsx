import '@testing-library/jest-dom/vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initAppearanceFromStorage, setColorScheme } from '../lib/appearance.ts'
import { initLanguageFromStorage, messages, setAppLanguage, t } from '../lib/language.ts'
import { toast } from '../lib/toast.ts'
import {
  COOKIE_KEYS,
  resetCookieStore,
  resetSettingsStore,
  setCookieStore,
  setSettingsStore,
} from '../lib/settings.ts'
import {
  readValidGooglePhotosAccessToken,
  resetGooglePhotosSessionStore,
  setGooglePhotosSessionStore,
  writeGooglePhotosSession,
} from '../storage/googlePhotosSession.ts'
import {
  MemoryCookieStrategy,
  MemoryRouterHarness,
  SAMPLE_SETTINGS,
  SpyKvStore,
  jsonResponse,
} from '../testing/index.ts'

const SETTINGS = SAMPLE_SETTINGS
const routes = new MemoryRouterHarness()

function renderAt(path: string) {
  return routes.renderApp(path)
}

function patchMaxConcurrent(fetchMock: ReturnType<typeof vi.fn>, expected: number): boolean {
  return fetchMock.mock.calls.some((call) => {
    if (!String(call[0]).endsWith('/api/settings')) {
      return false
    }
    const init = call[1] as RequestInit | undefined
    if (init?.method !== 'PATCH') {
      return false
    }
    return JSON.parse(String(init.body)).max_concurrent_jobs === expected
  })
}

describe('Settings language', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(SETTINGS)),
    )
  })

  afterEach(() => {
    setAppLanguage('he', false)
    setColorScheme('light', false)
    resetSettingsStore()
    resetCookieStore()
    resetGooglePhotosSessionStore()
    toast.clear()
    vi.unstubAllGlobals()
  })

  it('does not persist language until Save', async () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    initLanguageFromStorage()
    renderAt('/settings')

    fireEvent.click(screen.getByRole('radio', { name: 'English' }))

    expect(store.set).not.toHaveBeenCalled()
    expect(screen.getByRole('radio', { name: 'English' })).toBeChecked()
    expect(screen.getByRole('heading', { name: messages.he.settingsHeading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: messages.he.navSettings })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: t.save }))

    await waitFor(() => {
      expect(store.set).toHaveBeenCalledWith('language', 'en')
    })
    expect(screen.getByRole('link', { name: messages.en.navSettings })).toHaveAttribute(
      'href',
      '/settings',
    )
    expect(screen.getByRole('heading', { name: messages.en.settingsHeading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: messages.en.navAlbums })).toBeInTheDocument()
  })

  it('uses stored language on boot', () => {
    const store = new SpyKvStore({ language: 'en' })
    setSettingsStore(store)
    initLanguageFromStorage()
    renderAt('/settings')

    expect(screen.getByRole('link', { name: messages.en.navSettings })).toHaveAttribute(
      'href',
      '/settings',
    )
    expect(screen.getByRole('heading', { name: messages.en.settingsHeading })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'English' })).toBeChecked()
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('can switch the draft language back to Hebrew before save', () => {
    renderAt('/settings')
    fireEvent.click(screen.getByRole('radio', { name: 'English' }))
    fireEvent.click(screen.getByRole('radio', { name: 'עברית' }))
    expect(screen.getByRole('radio', { name: 'עברית' })).toBeChecked()
    expect(screen.getByRole('heading', { name: messages.he.settingsHeading })).toBeInTheDocument()
  })
})

describe('Settings import cookies', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(SETTINGS)),
    )
  })

  afterEach(() => {
    setAppLanguage('he', false)
    setColorScheme('light', false)
    resetSettingsStore()
    resetCookieStore()
    resetGooglePhotosSessionStore()
    toast.clear()
    vi.unstubAllGlobals()
  })

  it('clear button removes cached import headers', () => {
    const cookies = new MemoryCookieStrategy({
      [COOKIE_KEYS.importHeaders]: JSON.stringify({ Cookie: 'session=abc' }),
      [COOKIE_KEYS.cacheHeaders]: '0',
    })
    setCookieStore(cookies)
    renderAt('/settings')

    fireEvent.click(screen.getByRole('button', { name: t.settingsClearCookies }))

    expect(cookies.get(COOKIE_KEYS.importHeaders)).toBeNull()
    expect(cookies.get(COOKIE_KEYS.cacheHeaders)).toBe('0')
  })
})

describe('Settings Google Photos sign-out', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(SETTINGS)),
    )
  })

  afterEach(() => {
    setAppLanguage('he', false)
    setColorScheme('light', false)
    resetSettingsStore()
    resetCookieStore()
    resetGooglePhotosSessionStore()
    toast.clear()
    vi.unstubAllGlobals()
  })

  it('clears the saved Photos session', () => {
    const kv = new SpyKvStore()
    setGooglePhotosSessionStore(kv)
    writeGooglePhotosSession('ya29.tok', 3600)
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.tok')
    renderAt('/settings')

    fireEvent.click(screen.getByRole('button', { name: t.settingsSignOutGoogle }))

    expect(readValidGooglePhotosAccessToken()).toBeNull()
  })
})

describe('Settings appearance', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(SETTINGS)),
    )
  })

  afterEach(() => {
    setAppLanguage('he', false)
    setColorScheme('light', false)
    resetSettingsStore()
    resetCookieStore()
    resetGooglePhotosSessionStore()
    toast.clear()
    vi.unstubAllGlobals()
  })

  it('applies appearance immediately without Save', () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    renderAt('/settings')

    fireEvent.click(screen.getByRole('radio', { name: t.appearanceDark }))

    expect(store.set).toHaveBeenCalledWith('colorScheme', 'dark')
    expect(document.documentElement.dataset.colorScheme).toBe('dark')
    expect(screen.getByRole('radio', { name: t.appearanceDark })).toBeChecked()
    expect(screen.getByRole('heading', { name: messages.he.settingsHeading })).toBeInTheDocument()
  })

  it('uses stored appearance on boot', () => {
    const store = new SpyKvStore({ colorScheme: 'dark' })
    setSettingsStore(store)
    initAppearanceFromStorage()
    renderAt('/settings')

    expect(screen.getByRole('radio', { name: t.appearanceDark })).toBeChecked()
    expect(document.documentElement.dataset.colorScheme).toBe('dark')
  })
})

describe('Settings max concurrent jobs', () => {
  afterEach(() => {
    setAppLanguage('he', false)
    setColorScheme('light', false)
    resetSettingsStore()
    resetCookieStore()
    resetGooglePhotosSessionStore()
    toast.clear()
    vi.unstubAllGlobals()
  })

  it('shows the running app version from the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/version')) {
          return jsonResponse({ version: '1.0.0' })
        }
        return jsonResponse(SETTINGS)
      }),
    )
    renderAt('/settings')

    expect(await screen.findByText(t.settingsVersionHeading)).toBeInTheDocument()
    const versions = await screen.findAllByText(t.settingsVersionValue('1.0.0'))
    expect(versions.length).toBeGreaterThanOrEqual(1)
  })

  it('has exactly one Save button and a separate clear-cookies action', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ max_concurrent_jobs: 3, pending: 0, running: 0, waiting: 0 })),
    )
    renderAt('/settings')

    await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    expect(screen.getAllByRole('button', { name: t.save })).toHaveLength(1)
    expect(screen.getByRole('button', { name: t.settingsClearCookies })).toBeInTheDocument()
  })

  it('shows a tooltip next to max concurrent explaining raise vs lower', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(SETTINGS)),
    )
    renderAt('/settings')

    const input = await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    const info = screen.getByRole('button', { name: t.settingsMaxConcurrentInfoAria })
    expect(input.closest('.settings-page__field')).toContainElement(info)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.focus(info)
    expect(screen.getByRole('tooltip')).toHaveTextContent(t.settingsMaxConcurrentTooltip)
    expect(info).toHaveAccessibleDescription(t.settingsMaxConcurrentTooltip)

    fireEvent.blur(info)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseEnter(info)
    expect(screen.getByRole('tooltip')).toHaveTextContent(t.settingsMaxConcurrentTooltip)
  })

  it('defaults max concurrent input to 3 before settings load', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    )
    renderAt('/settings')

    expect(screen.getByLabelText(t.settingsMaxConcurrentLabel)).toHaveValue(3)
  })

  it('loads and saves max concurrent jobs via the API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/settings') && (!init || init.method === 'GET')) {
        return jsonResponse(SETTINGS)
      }
      if (url.endsWith('/api/settings') && init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body)) as { max_concurrent_jobs: number }
        return jsonResponse({ ...SETTINGS, max_concurrent_jobs: body.max_concurrent_jobs })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/settings')

    const input = await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    expect(input).toHaveValue(2)

    fireEvent.change(input, { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: t.save }))

    await waitFor(() => {
      expect(patchMaxConcurrent(fetchMock, 5)).toBe(true)
    })
  })

  it('saves language and max concurrent with one click', async () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/settings') && (!init || init.method === 'GET')) {
        return jsonResponse({ max_concurrent_jobs: 3, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/api/settings') && init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body)) as { max_concurrent_jobs: number }
        return jsonResponse({
          max_concurrent_jobs: body.max_concurrent_jobs,
          pending: 0,
          running: 0,
          waiting: 0,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/settings')

    fireEvent.click(screen.getByRole('radio', { name: 'English' }))
    const input = await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    fireEvent.change(input, { target: { value: '5' } })

    expect(store.set).not.toHaveBeenCalled()
    expect(screen.getAllByRole('button', { name: t.save })).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: t.save }))

    expect(store.set).toHaveBeenCalledWith('language', 'en')
    await waitFor(() => {
      expect(patchMaxConcurrent(fetchMock, 5)).toBe(true)
    })
    expect(screen.getByRole('heading', { name: messages.en.settingsHeading })).toBeInTheDocument()
  })

  it('shows a queue error when settings fail to load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'down' }, 503)),
    )
    renderAt('/settings')

    expect(await screen.findByRole('alert')).toHaveTextContent(/503/)
  })

  it('rejects a non-numeric max concurrent value without PATCHing', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/settings') && (!init || init.method === 'GET')) {
        return jsonResponse(SETTINGS)
      }
      if (url.endsWith('/api/settings') && init?.method === 'PATCH') {
        throw new Error('PATCH should not run for invalid input')
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/settings')

    const input = await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    fireEvent.change(input, { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: t.save }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.settingsOrchestratorError('invalid number'),
    )
    expect(
      fetchMock.mock.calls.some((call) => (call[1] as RequestInit | undefined)?.method === 'PATCH'),
    ).toBe(false)
  })

  it('keeps language when queue PATCH fails', async () => {
    const store = new SpyKvStore()
    setSettingsStore(store)
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/settings') && (!init || init.method === 'GET')) {
        return jsonResponse({ max_concurrent_jobs: 3, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/api/settings') && init?.method === 'PATCH') {
        return jsonResponse({ detail: 'server exploded' }, 500)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/settings')

    fireEvent.click(screen.getByRole('radio', { name: 'English' }))
    await screen.findByLabelText(t.settingsMaxConcurrentLabel)
    fireEvent.click(screen.getByRole('button', { name: t.save }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      messages.en.settingsOrchestratorError('HTTP 500: server exploded'),
    )
    expect(store.set).toHaveBeenCalledWith('language', 'en')
    expect(screen.getByRole('heading', { name: messages.en.settingsHeading })).toBeInTheDocument()
  })
})
