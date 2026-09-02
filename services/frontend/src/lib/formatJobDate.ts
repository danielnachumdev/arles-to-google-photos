import { APP_LANGUAGE, t } from './language.ts'

export function formatJobDate(iso: string | null | undefined): string {
  if (!iso) {
    return t.missingValue
  }
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    return t.missingValue
  }
  return parsed.toLocaleString(APP_LANGUAGE === 'he' ? 'he-IL' : 'en-US')
}
