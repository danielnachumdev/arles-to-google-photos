import { en } from './en.ts'
import { he } from './he.ts'
import type { AppLanguage, MessageCatalog, TextDirection } from './messages.ts'

export const messages: Record<AppLanguage, MessageCatalog> = {
  he,
  en,
}

export const LANGUAGE_DIR: Record<AppLanguage, TextDirection> = {
  he: 'rtl',
  en: 'ltr',
}
