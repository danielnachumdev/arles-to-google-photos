import { useSyncExternalStore } from 'react'
import {
  readColorSchemeSetting,
  writeColorSchemeSetting,
  type ColorScheme,
} from './settings.ts'

export type { ColorScheme }

const DEFAULT_COLOR_SCHEME: ColorScheme = 'light'

export let APP_COLOR_SCHEME: ColorScheme = DEFAULT_COLOR_SCHEME

const appearanceListeners = new Set<() => void>()
let appearanceEpoch = 0

export function subscribeAppearance(onStoreChange: () => void): () => void {
  appearanceListeners.add(onStoreChange)
  return () => {
    appearanceListeners.delete(onStoreChange)
  }
}

export function getAppearanceSnapshot(): number {
  return appearanceEpoch
}

export function getColorScheme(): ColorScheme {
  return APP_COLOR_SCHEME
}

export function applyDocumentColorScheme(): void {
  document.documentElement.dataset.colorScheme = APP_COLOR_SCHEME
}

export function setColorScheme(next: ColorScheme, persist = true): void {
  if (persist) {
    writeColorSchemeSetting(next)
  }
  if (next === APP_COLOR_SCHEME) {
    applyDocumentColorScheme()
    return
  }
  APP_COLOR_SCHEME = next
  applyDocumentColorScheme()
  appearanceEpoch += 1
  appearanceListeners.forEach((listener) => listener())
}

export function initAppearanceFromStorage(): void {
  const stored = readColorSchemeSetting()
  setColorScheme(stored ?? DEFAULT_COLOR_SCHEME, false)
  applyDocumentColorScheme()
}

export type UseAppearanceResult = {
  colorScheme: ColorScheme
  setColorScheme: (next: ColorScheme, persist?: boolean) => void
}

export function useAppearance(): UseAppearanceResult {
  useSyncExternalStore(subscribeAppearance, getAppearanceSnapshot, getAppearanceSnapshot)
  return {
    colorScheme: getColorScheme(),
    setColorScheme,
  }
}
