import { describe, expect, it } from 'vitest'
import type { JobSummary } from '../api/types.ts'
import { t } from './language.ts'
import {
  formatJobDuration,
  isJobActive,
  isJobArchivable,
  isJobCancellable,
  isJobProcessing,
  jobDurationSeconds,
} from './formatJobDuration.ts'

function summary(overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id: 'job-1',
    status: 'done',
    type: 'preview',
    error: null,
    title: 'Album',
    item_count: 1,
    created_at: '2026-08-08T10:00:00.000Z',
    product_url: null,
    ...overrides,
  }
}

describe('formatJobDuration', () => {
  it('formats minutes and hours with zero-padded seconds', () => {
    expect(formatJobDuration(0)).toBe('0:00')
    expect(formatJobDuration(12)).toBe('0:12')
    expect(formatJobDuration(75)).toBe('1:15')
    expect(formatJobDuration(3661)).toBe('1:01:01')
  })

  it('returns the missing placeholder for empty values', () => {
    expect(formatJobDuration(null)).toBe(t.missingValue)
    expect(formatJobDuration(undefined)).toBe(t.missingValue)
    expect(formatJobDuration(Number.NaN)).toBe(t.missingValue)
    expect(formatJobDuration(-1)).toBe(t.missingValue)
  })
})

describe('jobDurationSeconds', () => {
  it('uses server duration when the job is terminal', () => {
    expect(
      jobDurationSeconds(summary({ duration_seconds: 45, status: 'done' }), Date.parse('2026-08-08T10:10:00.000Z')),
    ).toBe(45)
  })

  it('ticks from running_started_at while running, ignoring pending created_at', () => {
    const now = Date.parse('2026-08-08T10:00:09.000Z')
    expect(
      jobDurationSeconds(
        summary({
          status: 'running',
          duration_seconds: 0,
          created_at: '2026-08-08T09:50:00.000Z',
          running_started_at: '2026-08-08T10:00:00.000Z',
          started_at: '2026-08-08T10:00:00.000Z',
        }),
        now,
      ),
    ).toBe(9)
  })

  it('uses the larger of server snapshot and live running elapsed', () => {
    const now = Date.parse('2026-08-08T10:00:03.000Z')
    expect(
      jobDurationSeconds(
        summary({
          status: 'running',
          duration_seconds: 12,
          running_started_at: '2026-08-08T10:00:00.000Z',
          started_at: '2026-08-08T09:59:00.000Z',
        }),
        now,
      ),
    ).toBe(12)
  })

  it('does not count waiting or pending time from created_at', () => {
    const now = Date.parse('2026-08-08T12:00:00.000Z')
    expect(
      jobDurationSeconds(
        summary({
          status: 'waiting',
          duration_seconds: 8,
          created_at: '2026-08-08T10:00:00.000Z',
        }),
        now,
      ),
    ).toBe(8)
    expect(
      jobDurationSeconds(
        summary({ status: 'pending', duration_seconds: null, created_at: '2026-08-08T10:00:00.000Z' }),
        now,
      ),
    ).toBeNull()
  })

  it('returns stored duration when running_started_at cannot be parsed', () => {
    expect(
      jobDurationSeconds(
        summary({
          created_at: 'not-a-date',
          running_started_at: 'also-bad',
          duration_seconds: 12,
          status: 'running',
        }),
        Date.parse('2026-08-08T10:10:00.000Z'),
      ),
    ).toBe(12)
  })

  it('falls back to finished_at for terminal jobs without duration_seconds', () => {
    expect(
      jobDurationSeconds(
        summary({
          status: 'done',
          duration_seconds: null,
          finished_at: '2026-08-08T10:02:30.000Z',
        }),
        Date.parse('2026-08-08T12:00:00.000Z'),
      ),
    ).toBe(150)
  })
})

describe('isJobProcessing', () => {
  it('treats running and waiting as live work', () => {
    expect(isJobProcessing('running')).toBe(true)
    expect(isJobProcessing('waiting')).toBe(true)
    expect(isJobProcessing('pending')).toBe(false)
    expect(isJobProcessing('done')).toBe(false)
    expect(isJobProcessing('failed')).toBe(false)
    expect(isJobProcessing('cancelled')).toBe(false)
  })
})

describe('isJobActive', () => {
  it('treats pending, running, and waiting as in-flight', () => {
    expect(isJobActive('pending')).toBe(true)
    expect(isJobActive('running')).toBe(true)
    expect(isJobActive('waiting')).toBe(true)
    expect(isJobActive('done')).toBe(false)
    expect(isJobActive('failed')).toBe(false)
    expect(isJobActive('cancelled')).toBe(false)
  })
})

describe('isJobCancellable', () => {
  it('treats pending, running, and waiting as cancellable', () => {
    expect(isJobCancellable('pending')).toBe(true)
    expect(isJobCancellable('running')).toBe(true)
    expect(isJobCancellable('waiting')).toBe(true)
    expect(isJobCancellable('done')).toBe(false)
    expect(isJobCancellable('failed')).toBe(false)
    expect(isJobCancellable('cancelled')).toBe(false)
  })
})

describe('isJobArchivable', () => {
  it('treats done, failed, and cancelled as archivable', () => {
    expect(isJobArchivable('done')).toBe(true)
    expect(isJobArchivable('failed')).toBe(true)
    expect(isJobArchivable('cancelled')).toBe(true)
    expect(isJobArchivable('pending')).toBe(false)
    expect(isJobArchivable('running')).toBe(false)
    expect(isJobArchivable('waiting')).toBe(false)
  })
})
