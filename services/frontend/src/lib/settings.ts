import { createDocumentCookieStore, type CookieStore } from '../storage/cookies.ts'
import { createLocalStorageStore, type KeyValueStore } from '../storage/kv.ts'
import { APP_LANGUAGES, type AppLanguage } from './i18n/messages.ts'

export const COLOR_SCHEMES = ['light', 'dark'] as const

export type ColorScheme = (typeof COLOR_SCHEMES)[number]

export const IMPORT_MODES = ['upload', 'web'] as const

export type ImportModeSetting = (typeof IMPORT_MODES)[number]

export const DEFAULT_IMPORT_MODE: ImportModeSetting = 'upload'

export const SETTINGS_CHANGED_EVENT = 'arles-settings-changed'

export const SETTINGS_KEYS = {
  language: 'language',
  colorScheme: 'colorScheme',
  defaultImportMode: 'defaultImportMode',
} as const

export const COOKIE_KEYS = {
  importHeaders: 'arles.import.headers',
  cacheHeaders: 'arles.import.cacheHeaders',
} as const

let store: KeyValueStore = createLocalStorageStore()
let cookies: CookieStore = createDocumentCookieStore()

export function setSettingsStore(next: KeyValueStore): void {
  store = next
}

export function resetSettingsStore(): void {
  store = createLocalStorageStore()
}

export function setCookieStore(next: CookieStore): void {
  cookies = next
}

export function resetCookieStore(): void {
  cookies = createDocumentCookieStore()
}

export function parseAppLanguage(value: string | null): AppLanguage | null {
  for (const language of APP_LANGUAGES) {
    if (value === language) {
      return language
    }
  }
  return null
}

export function readLanguageSetting(): AppLanguage | null {
  return parseAppLanguage(store.get(SETTINGS_KEYS.language))
}

export function writeLanguageSetting(language: AppLanguage): void {
  store.set(SETTINGS_KEYS.language, language)
}

export function parseColorScheme(value: string | null): ColorScheme | null {
  for (const scheme of COLOR_SCHEMES) {
    if (value === scheme) {
      return scheme
    }
  }
  return null
}

export function readColorSchemeSetting(): ColorScheme | null {
  return parseColorScheme(store.get(SETTINGS_KEYS.colorScheme))
}

export function writeColorSchemeSetting(scheme: ColorScheme): void {
  store.set(SETTINGS_KEYS.colorScheme, scheme)
}

function notifySettingsChanged(): void {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new Event(SETTINGS_CHANGED_EVENT))
}

export function parseImportModeSetting(value: string | null): ImportModeSetting | null {
  for (const mode of IMPORT_MODES) {
    if (value === mode) {
      return mode
    }
  }
  return null
}

export function readDefaultImportMode(): ImportModeSetting {
  return parseImportModeSetting(store.get(SETTINGS_KEYS.defaultImportMode)) ?? DEFAULT_IMPORT_MODE
}

export function writeDefaultImportMode(mode: ImportModeSetting): void {
  store.set(SETTINGS_KEYS.defaultImportMode, mode)
  notifySettingsChanged()
}

export function readCachedImportHeaders(): Record<string, string> | null {
  const raw = cookies.get(COOKIE_KEYS.importHeaders)
  if (!raw) {
    return null
  }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    const headers: Record<string, string> = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string' && key.trim()) {
        headers[key] = value
      }
    }
    return Object.keys(headers).length > 0 ? headers : null
  } catch {
    return null
  }
}

export function writeCachedImportHeaders(headers: Record<string, string>): void {
  cookies.set(COOKIE_KEYS.importHeaders, JSON.stringify(headers))
}

export function readCacheHeadersToggle(): boolean {
  const raw = cookies.get(COOKIE_KEYS.cacheHeaders)
  if (raw === null) {
    return true
  }
  return raw === '1' || raw === 'true'
}

export function writeCacheHeadersToggle(enabled: boolean): void {
  cookies.set(COOKIE_KEYS.cacheHeaders, enabled ? '1' : '0')
}

export function clearImportCookies(): void {
  cookies.remove(COOKIE_KEYS.importHeaders)
}
