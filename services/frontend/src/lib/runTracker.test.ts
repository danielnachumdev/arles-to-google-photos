import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { t } from './language.ts'
import {
  announceRunSubmitted,
  clearTrackedRuns,
  consumeRunToast,
  diffListedJobs,
  getTrackedRuns,
  jobToastLabel,
  kindFromJobType,
  rememberListedJobs,
  subscribeTrackedRuns,
  trackRun,
} from './runTracker.ts'
import { getToasts, toast } from './toast.ts'

describe('runTracker', () => {
  beforeEach(() => {
    toast.clear()
    clearTrackedRuns()
  })

  afterEach(() => {
    toast.clear()
    clearTrackedRuns()
  })

  it('kindFromJobType maps scrape separately from preview and upload', () => {
    expect(kindFromJobType('upload')).toBe('upload')
    expect(kindFromJobType('scrape')).toBe('scrape')
    expect(kindFromJobType('preview')).toBe('preview')
    expect(kindFromJobType(undefined)).toBe('preview')
  })

  it('jobToastLabel prefers a finite number over the id', () => {
    expect(jobToastLabel('job-uuid', 12)).toBe('#12')
    expect(jobToastLabel('job-uuid', 0)).toBe('#0')
    expect(jobToastLabel('job-uuid', Number.NaN)).toBe('job-uuid')
    expect(jobToastLabel('job-uuid', null)).toBe('job-uuid')
    expect(jobToastLabel('job-uuid')).toBe('job-uuid')
  })

  it('announceRunSubmitted shows an info toast with a job link', () => {
    announceRunSubmitted('job-42')
    expect(getToasts()).toEqual([
      expect.objectContaining({
        type: 'regular',
        message: t.toastRunSubmitted(jobToastLabel('job-42')),
        href: '/jobs/job-42',
        linkLabel: t.toastOpenRun,
      }),
    ])
  })

  it('announceRunSubmitted includes the job number when present', () => {
    announceRunSubmitted('job-uuid', 12)
    expect(getToasts()).toEqual([
      expect.objectContaining({
        type: 'regular',
        message: t.toastRunSubmitted('#12'),
        href: '/jobs/job-uuid',
        linkLabel: t.toastOpenRun,
      }),
    ])
  })

  it('announceRunSubmitted is idempotent until the run completes again', () => {
    announceRunSubmitted('job-1')
    announceRunSubmitted('job-1')
    expect(getToasts()).toHaveLength(1)
    expect(consumeRunToast('job-1')).toBe(true)
    expect(consumeRunToast('job-1')).toBe(false)
    toast.clear()
    announceRunSubmitted('job-1')
    expect(getToasts()).toEqual([
      expect.objectContaining({
        type: 'regular',
        message: t.toastRunSubmitted(jobToastLabel('job-1')),
        href: '/jobs/job-1',
      }),
    ])
    expect(consumeRunToast('job-1')).toBe(true)
  })

  it('tracks a run once and notifies subscribers', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeTrackedRuns(listener)
    trackRun({ id: 'job-1', kind: 'preview', status: 'running' })
    trackRun({ id: 'job-1', kind: 'preview', status: 'running' })
    expect(getTrackedRuns()).toEqual([{ id: 'job-1', kind: 'preview', status: 'running' }])
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
    trackRun({ id: 'job-2', kind: 'upload' })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(getTrackedRuns().map((run) => run.id)).toEqual(['job-1', 'job-2'])
  })

  it('diffListedJobs reports new ids and status transitions after a snapshot', () => {
    const known = new Map([
      ['old-done', 'done' as const],
      ['running-1', 'running' as const],
    ])
    const listed = [
      { id: 'old-done', status: 'done' as const, type: 'preview' },
      { id: 'running-1', status: 'done' as const, type: 'upload', error: null },
      { id: 'new-run', status: 'running' as const, type: 'upload' },
    ]
    const diff = diffListedJobs(known, listed)
    expect(diff.created).toEqual([
      expect.objectContaining({ id: 'new-run', status: 'running' }),
    ])
    expect(diff.transitioned).toEqual([
      {
        job: expect.objectContaining({ id: 'running-1', status: 'done' }),
        from: 'running',
      },
    ])
    rememberListedJobs(known, listed)
    expect(diffListedJobs(known, listed)).toEqual({ created: [], transitioned: [] })
  })
})
