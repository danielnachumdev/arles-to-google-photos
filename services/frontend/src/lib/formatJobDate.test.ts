import { afterEach, describe, expect, it } from 'vitest'
import { setAppLanguage, t } from './language.ts'
import { formatJobDate } from './formatJobDate.ts'

describe('formatJobDate', () => {
  afterEach(() => {
    setAppLanguage('he', false)
  })

  it('returns the missing placeholder for empty or invalid values', () => {
    expect(formatJobDate(null)).toBe(t.missingValue)
    expect(formatJobDate(undefined)).toBe(t.missingValue)
    expect(formatJobDate('')).toBe(t.missingValue)
    expect(formatJobDate('not-a-date')).toBe(t.missingValue)
  })

  it('formats a valid ISO timestamp for the active language', () => {
    setAppLanguage('en', false)
    const formatted = formatJobDate('2012-08-02T10:00:00+00:00')
    expect(formatted).not.toBe(t.missingValue)
    expect(formatted.length).toBeGreaterThan(4)
  })
})
