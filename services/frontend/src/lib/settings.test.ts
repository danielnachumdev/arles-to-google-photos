import { afterEach, describe, expect, it } from 'vitest'
import { MemoryCookieStrategy, SpyKvStore } from '../testing/index.ts'
import {
  COOKIE_KEYS,
  clearImportCookies,
  parseAppLanguage,
  parseColorScheme,
  readCacheHeadersToggle,
  readCachedImportHeaders,
  readColorSchemeSetting,
  readLanguageSetting,
  resetCookieStore,
  resetSettingsStore,
  setCookieStore,
  setSettingsStore,
  writeCacheHeadersToggle,
  writeCachedImportHeaders,
  writeColorSchemeSetting,
  writeLanguageSetting,
} from './settings.ts'

describe('settings cookie helpers', () => {
  afterEach(() => {
    resetCookieStore()
    resetSettingsStore()
  })

  it('parses and persists language settings', () => {
    const kv = new SpyKvStore()
    setSettingsStore(kv)
    expect(parseAppLanguage(null)).toBeNull()
    expect(parseAppLanguage('fr')).toBeNull()
    expect(parseAppLanguage('en')).toBe('en')
    expect(readLanguageSetting()).toBeNull()
    writeLanguageSetting('he')
    expect(kv.set).toHaveBeenCalledWith('language', 'he')
    expect(readLanguageSetting()).toBe('he')
  })

  it('parses and persists color scheme settings', () => {
    const kv = new SpyKvStore()
    setSettingsStore(kv)
    expect(parseColorScheme(null)).toBeNull()
    expect(parseColorScheme('system')).toBeNull()
    expect(parseColorScheme('dark')).toBe('dark')
    expect(readColorSchemeSetting()).toBeNull()
    writeColorSchemeSetting('dark')
    expect(kv.set).toHaveBeenCalledWith('colorScheme', 'dark')
    expect(readColorSchemeSetting()).toBe('dark')
  })

  it('ignores invalid cached import header JSON', () => {
    const cookies = new MemoryCookieStrategy({
      [COOKIE_KEYS.importHeaders]: '{not-json',
    })
    setCookieStore(cookies)
    expect(readCachedImportHeaders()).toBeNull()

    cookies.set(COOKIE_KEYS.importHeaders, JSON.stringify(['x']))
    expect(readCachedImportHeaders()).toBeNull()

    cookies.set(COOKIE_KEYS.importHeaders, JSON.stringify({ Cookie: 1 }))
    expect(readCachedImportHeaders()).toBeNull()
  })

  it('reads and writes cached import headers', () => {
    const store = new MemoryCookieStrategy()
    setCookieStore(store)
    expect(readCachedImportHeaders()).toBeNull()

    writeCachedImportHeaders({ Cookie: 'session=abc' })

    expect(store.get(COOKIE_KEYS.importHeaders)).toBe(
      JSON.stringify({ Cookie: 'session=abc' }),
    )
    expect(readCachedImportHeaders()).toEqual({ Cookie: 'session=abc' })
  })

  it('defaults the cache-headers toggle to on', () => {
    const store = new MemoryCookieStrategy()
    setCookieStore(store)
    expect(readCacheHeadersToggle()).toBe(true)

    writeCacheHeadersToggle(false)

    expect(store.get(COOKIE_KEYS.cacheHeaders)).toBe('0')
    expect(readCacheHeadersToggle()).toBe(false)

    writeCacheHeadersToggle(true)
    expect(readCacheHeadersToggle()).toBe(true)
  })

  it('clearImportCookies removes cached headers but keeps the toggle', () => {
    const store = new MemoryCookieStrategy()
    setCookieStore(store)
    writeCachedImportHeaders({ Cookie: 'session=abc' })
    writeCacheHeadersToggle(false)

    clearImportCookies()

    expect(readCachedImportHeaders()).toBeNull()
    expect(store.get(COOKIE_KEYS.importHeaders)).toBeNull()
    expect(readCacheHeadersToggle()).toBe(false)
  })
})
