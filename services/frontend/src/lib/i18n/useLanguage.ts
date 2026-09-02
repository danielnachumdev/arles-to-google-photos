import { useSyncExternalStore } from 'react'
import type { AppLanguage, MessageCatalog, TextDirection } from './messages.ts'
import {
  APP_DIR,
  getAppLanguage,
  getLanguageSnapshot,
  setAppLanguage,
  subscribeLanguage,
  t,
} from './store.ts'

export type UseLanguageResult = {
  language: AppLanguage
  dir: TextDirection
  t: MessageCatalog
  setLanguage: (next: AppLanguage, persist?: boolean) => void
}

export function useLanguage(): UseLanguageResult {
  useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getLanguageSnapshot)
  return {
    language: getAppLanguage(),
    dir: APP_DIR,
    t,
    setLanguage: setAppLanguage,
  }
}
