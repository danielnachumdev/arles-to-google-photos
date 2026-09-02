import { readLanguageSetting, writeLanguageSetting } from '../settings.ts'
import { LANGUAGE_DIR, messages } from './catalogs.ts'
import type { AppLanguage, MessageCatalog, TextDirection } from './messages.ts'

const DEFAULT_LANGUAGE: AppLanguage = 'he'

export let APP_LANGUAGE: AppLanguage = DEFAULT_LANGUAGE

export let APP_DIR: TextDirection = LANGUAGE_DIR[APP_LANGUAGE]

const languageListeners = new Set<() => void>()
let languageEpoch = 0

export function subscribeLanguage(onStoreChange: () => void): () => void {
  languageListeners.add(onStoreChange)
  return () => {
    languageListeners.delete(onStoreChange)
  }
}

export function getLanguageSnapshot(): number {
  return languageEpoch
}

export function getAppLanguage(): AppLanguage {
  return APP_LANGUAGE
}

export function setAppLanguage(next: AppLanguage, persist = true): void {
  if (persist) {
    writeLanguageSetting(next)
  }
  if (next === APP_LANGUAGE) {
    return
  }
  APP_LANGUAGE = next
  APP_DIR = LANGUAGE_DIR[next]
  t = messages[next]
  applyDocumentLanguage()
  languageEpoch += 1
  languageListeners.forEach((listener) => listener())
}

export function initLanguageFromStorage(): void {
  const stored = readLanguageSetting()
  setAppLanguage(stored ?? DEFAULT_LANGUAGE, false)
  applyDocumentLanguage()
}

export let t: MessageCatalog = messages[APP_LANGUAGE]

export function jobStatusLabel(status: string): string {
  switch (status) {
    case 'pending':
      return t.statusPending
    case 'running':
      return t.statusRunning
    case 'waiting':
      return t.statusWaiting
    case 'done':
      return t.statusDone
    case 'failed':
      return t.statusFailed
    case 'cancelled':
      return t.statusCancelled
    default:
      return status
  }
}

export function jobTypeLabel(jobType: string): string {
  switch (jobType) {
    case 'preview':
      return t.typePreview
    case 'upload':
      return t.typeUpload
    case 'scrape':
      return t.typeScrape
    default:
      return jobType
  }
}

export function applyDocumentLanguage(): void {
  document.documentElement.lang = APP_LANGUAGE
  document.documentElement.dir = APP_DIR
  document.title = t.documentTitle
}
