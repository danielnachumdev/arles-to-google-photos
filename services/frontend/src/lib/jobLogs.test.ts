import { describe, expect, it } from 'vitest'
import type { JobEvent } from '../api/types.ts'
import {
  formatLogTime,
  inferJobEventAudience,
  inferJobEventKind,
  isLifecycleJobEvent,
  isOpsJobEvent,
  jobLogMessage,
  jobLogTone,
  shouldShowJobLog,
} from './jobLogs.ts'

function event(overrides: Partial<JobEvent> = {}): JobEvent {
  return {
    job_id: 'job-1',
    stage: 'scrape',
    message: 'Fetching gallery index',
    current: 0,
    total: 16,
    extra: null,
    occurred_at: '2012-08-02T18:04:12+00:00',
    ...overrides,
  }
}

describe('jobLogs', () => {
  it('treats scrape/parse/publish/ingest as ui logs and terminals as lifecycle', () => {
    expect(inferJobEventKind(event({ stage: 'scrape' }))).toBe('log')
    expect(inferJobEventKind(event({ stage: 'parse' }))).toBe('log')
    expect(inferJobEventKind(event({ stage: 'publish' }))).toBe('log')
    expect(inferJobEventKind(event({ stage: 'ingest' }))).toBe('log')
    expect(inferJobEventKind(event({ stage: 'preview_ready' }))).toBe('lifecycle')
    expect(inferJobEventKind(event({ stage: 'done' }))).toBe('lifecycle')
    expect(inferJobEventKind(event({ stage: 'waiting' }))).toBe('lifecycle')
    expect(inferJobEventKind(event({ stage: 'cancelled' }))).toBe('lifecycle')
    expect(inferJobEventKind(event({ kind: 'progress', stage: 'child' }))).toBe('lifecycle')
  })

  it('hides ops lines unless technical logs are on', () => {
    const ops = event({ audience: 'ops', kind: 'log', message: 'GET https://example → 200' })
    const fetchPage = event({
      audience: 'ops',
      kind: 'log',
      message: 'Fetching image page 20120802_01: https://example/a.html',
    })
    const saved = event({
      audience: 'ui',
      kind: 'log',
      message: 'Saved hrimages/20120802_01hr.JPG · 1/2 · 12KB',
    })
    const ready = event({ stage: 'preview_ready', kind: 'lifecycle', message: 'Day 1' })
    expect(shouldShowJobLog(ops, false)).toBe(false)
    expect(shouldShowJobLog(ops, true)).toBe(true)
    expect(shouldShowJobLog(fetchPage, false)).toBe(false)
    expect(shouldShowJobLog(fetchPage, true)).toBe(true)
    expect(shouldShowJobLog(saved, false)).toBe(true)
    expect(shouldShowJobLog(ready, false)).toBe(true)
    expect(isOpsJobEvent(ops)).toBe(true)
    expect(inferJobEventAudience(ops)).toBe('ops')
  })

  it('uses the message, or a lifecycle label when the message is empty', () => {
    expect(jobLogMessage(event({ message: 'Fetching gallery index' }), () => 'Preview ready')).toBe(
      'Fetching gallery index',
    )
    expect(
      jobLogMessage(event({ stage: 'preview_ready', message: '', kind: 'lifecycle' }), (stage) =>
        stage === 'preview_ready' ? 'Preview ready' : stage,
      ),
    ).toBe('Preview ready')
  })

  it('formats a 24h clock time', () => {
    const formatted = formatLogTime('2012-08-02T18:04:12+00:00', 'en-US')
    expect(formatted).toMatch(/\d{2}:\d{2}:\d{2}/)
    expect(formatLogTime(null, 'en-US')).toBe('')
    expect(formatLogTime('not-a-date', 'en-US')).toBe('')
  })

  it('maps error and cancelled tones for lifecycle rows', () => {
    expect(jobLogTone(event({ stage: 'error' }))).toBe('error')
    expect(jobLogTone(event({ stage: 'failed' }))).toBe('error')
    expect(jobLogTone(event({ stage: 'cancelled' }))).toBe('cancelled')
    expect(jobLogTone(event({ stage: 'done' }))).toBeNull()
    expect(isLifecycleJobEvent(event({ stage: 'preview_ready' }))).toBe(true)
    expect(isLifecycleJobEvent(event({ stage: 'scrape' }))).toBe(false)
  })
})
