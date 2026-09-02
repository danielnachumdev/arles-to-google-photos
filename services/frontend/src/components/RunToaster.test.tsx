import '@testing-library/jest-dom/vitest'
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job, JobSummary } from '../api/types.ts'
import { t } from '../lib/language.ts'
import { announceRunSubmitted, clearTrackedRuns, jobToastLabel, trackRun } from '../lib/runTracker.ts'
import { getToasts, toast } from '../lib/toast.ts'
import { FakeEventSource, JobBuilder, jsonResponse } from '../testing/index.ts'
import { RunToaster } from './RunToaster.tsx'

const PREVIEW_DONE: Job = JobBuilder.preview({
  id: 'preview-1',
  preview: null,
  folder_label: undefined,
}).build()

const UPLOAD_FAILED: Job = JobBuilder.preview({
  id: 'upload-1',
  type: 'upload',
  status: 'failed',
  error: 'quota exceeded',
  preview: null,
  folder_label: undefined,
}).build()

describe('RunToaster', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    toast.clear()
    clearTrackedRuns()
    FakeEventSource.install()
    fetchMock = vi.fn(async () => jsonResponse({ detail: 'not found' }, 404))
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    toast.clear()
    clearTrackedRuns()
    vi.unstubAllGlobals()
    FakeEventSource.install()
    vi.restoreAllMocks()
  })

  it('toasts preview success in green when a tracked run is already done', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'good',
          message: t.toastPreviewDone(PREVIEW_DONE.id),
          href: `/jobs/${PREVIEW_DONE.id}`,
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
  })

  it('toasts preview success with the visible job number when present', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({ id: 'preview-num', kind: 'preview', status: 'done', number: 12 })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'good',
          message: t.toastPreviewDone('#12'),
          href: '/jobs/preview-num',
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
  })

  it('toasts scrape success without using preview copy', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({ id: 'scrape-1', kind: 'scrape', status: 'done', number: 8 })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'good',
          message: t.toastScrapeDone('#8'),
          href: '/jobs/scrape-1',
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
    expect(getToasts()[0]?.message).not.toBe(t.previewReady)
  })

  it('toasts cancellation without treating it as a failure', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({ id: 'scrape-3', kind: 'scrape', status: 'cancelled', number: 3 })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunCancelledJob('#3'),
          href: '/jobs/scrape-3',
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
    expect(getToasts()[0]?.type).not.toBe('bad')
  })

  it('toasts scrape failure with the error detail', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({
        id: 'scrape-2',
        kind: 'scrape',
        status: 'failed',
        error: 'unreachable host',
      })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'bad',
          message: t.toastScrapeFailed('scrape-2', t.errorScrape('unreachable host')),
          href: '/jobs/scrape-2',
        }),
      ])
    })
  })

  it('toasts unsupported scrape failure with Arles-specific copy', async () => {
    const url = 'https://albums.example/album/index2012.html'
    render(<RunToaster />)
    act(() => {
      trackRun({
        id: 'scrape-unsupported',
        kind: 'scrape',
        status: 'failed',
        error: `Not a supported Arles album: ${url}`,
        error_code: 'not_arles',
        scrape_url: url,
      })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'bad',
          message: t.toastScrapeFailed('scrape-unsupported', t.errorScrapeUnsupported(url)),
          href: '/jobs/scrape-unsupported',
        }),
      ])
    })
    expect(getToasts()[0]?.message).not.toContain('Check the URL and headers')
    expect(getToasts()[0]?.type).toBe('bad')
  })

  it('toasts upload failure in red with the error detail', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({
        id: UPLOAD_FAILED.id,
        kind: 'upload',
        status: 'failed',
        error: UPLOAD_FAILED.error,
      })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'bad',
          message: t.toastUploadFailed(UPLOAD_FAILED.id, 'quota exceeded'),
          href: `/jobs/${UPLOAD_FAILED.id}`,
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
  })

  it('toasts upload success after a publish SSE done event', async () => {
    let uploadStatus: 'running' | 'done' = 'running'
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/upload-live`)) {
        return jsonResponse({
          id: 'upload-live',
          number: 12,
          status: uploadStatus,
          type: 'upload',
          error: null,
          product_url: uploadStatus === 'done' ? 'https://photos.example/live' : null,
          preview: null,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(<RunToaster />)
    act(() => {
      trackRun({ id: 'upload-live', kind: 'upload', status: 'running' })
    })

    await waitFor(() => {
      expect(FakeEventSource.instances.some((source) => source.url.includes('upload-live'))).toBe(
        true,
      )
    })
    const source = FakeEventSource.instances.find((item) => item.url.includes('upload-live'))!
    expect(source.url).toContain('phase=publish')

    act(() => {
      uploadStatus = 'done'
      source.emit({
        job_id: 'upload-live',
        stage: 'done',
        message: 'https://photos.example/live',
        current: 1,
        total: 1,
        extra: null,
      })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'good',
          message: t.toastUploadDone('#12'),
          href: '/jobs/upload-live',
        }),
      ])
    })
  })

  it('toasts preview failure after an ingest SSE error', async () => {
    let previewStatus: 'running' | 'failed' = 'running'
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/jobs/preview-live')) {
        return jsonResponse({
          id: 'preview-live',
          status: previewStatus,
          type: 'preview',
          error: previewStatus === 'failed' ? 'missing index.html' : null,
          product_url: null,
          preview: null,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(<RunToaster />)
    act(() => {
      trackRun({ id: 'preview-live', kind: 'preview', status: 'running' })
    })

    await waitFor(() => {
      expect(FakeEventSource.instances[0]?.url).toBe('/api/jobs/preview-live/events')
    })

    act(() => {
      previewStatus = 'failed'
      FakeEventSource.instances[0]!.emit({
        job_id: 'preview-live',
        stage: 'error',
        message: 'missing index.html',
        current: 0,
        total: 0,
        extra: null,
      })
    })

    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'bad',
          message: t.toastPreviewFailed('preview-live', 'missing index.html'),
          href: '/jobs/preview-live',
        }),
      ])
    })
  })

  it('does not toast the same run twice', async () => {
    render(<RunToaster />)
    act(() => {
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
    })

    await waitFor(() => {
      expect(getToasts()).toHaveLength(1)
    })
    act(() => {
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
    })
    expect(getToasts()).toHaveLength(1)
  })

  it('does not toast jobs that already existed in the opening snapshot', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).split('?')[0] === '/api/jobs') {
        return jsonResponse({
          jobs: [
            {
              id: PREVIEW_DONE.id,
              status: 'done',
              type: 'preview',
              error: null,
              title: 'Old album',
              item_count: 1,
              created_at: null,
              product_url: null,
            } satisfies JobSummary,
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(<RunToaster />)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).split('?')[0] === '/api/jobs')).toBe(
        true,
      )
    })
    expect(getToasts()).toEqual([])
  })

  it('info-toasts a job that appears after the snapshot', async () => {
    const intervals: Array<() => void> = []
    vi.spyOn(window, 'setInterval').mockImplementation((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        intervals.push(handler as () => void)
      }
      return 1 as unknown as number
    })
    vi.spyOn(window, 'clearInterval').mockImplementation(() => undefined)

    let listed: JobSummary[] = [
      {
        id: 'old-preview',
        status: 'done',
        type: 'preview',
        error: null,
        title: 'Old',
        item_count: 1,
        created_at: null,
        product_url: null,
      },
    ]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0]
      if (path === '/api/jobs') {
        return jsonResponse({ jobs: listed })
      }
      if (path.endsWith('/api/jobs/new-upload')) {
        return jsonResponse({
          id: 'new-upload',
          status: 'running',
          type: 'upload',
          error: null,
          product_url: null,
          preview: null,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(<RunToaster />)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).split('?')[0] === '/api/jobs')).toBe(
        true,
      )
    })
    expect(getToasts()).toEqual([])

    listed = [
      ...listed,
      {
        id: 'new-upload',
        number: 12,
        status: 'running',
        type: 'upload',
        error: null,
        title: null,
        item_count: 0,
        created_at: null,
        product_url: null,
      },
    ]
    await act(async () => {
      intervals.forEach((tick) => tick())
    })
    await waitFor(() => {
      expect(getToasts()).toEqual([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunSubmitted('#12'),
          href: '/jobs/new-upload',
          linkLabel: t.toastOpenRun,
        }),
      ])
    })
  })

  it('toasts completion again after the same preview id is resubmitted', async () => {
    render(<RunToaster />)
    act(() => {
      announceRunSubmitted(PREVIEW_DONE.id)
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
    })
    await waitFor(() => {
      expect(
        getToasts().some(
          (item) => item.type === 'good' && item.message === t.toastPreviewDone(PREVIEW_DONE.id),
        ),
      ).toBe(true)
    })
    toast.clear()
    act(() => {
      announceRunSubmitted(PREVIEW_DONE.id)
      trackRun({ id: PREVIEW_DONE.id, kind: 'preview', status: 'done' })
    })
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunSubmitted(jobToastLabel(PREVIEW_DONE.id)),
            href: `/jobs/${PREVIEW_DONE.id}`,
          }),
          expect.objectContaining({
            type: 'good',
            message: t.toastPreviewDone(PREVIEW_DONE.id),
            href: `/jobs/${PREVIEW_DONE.id}`,
          }),
        ]),
      )
    })
  })

  it('toasts preview success from a preview_ready SSE stage when getJob is still running', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/jobs/preview-ready')) {
        return jsonResponse({
          id: 'preview-ready',
          status: 'running',
          type: 'preview',
          error: null,
          product_url: null,
          preview: null,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(<RunToaster />)
    act(() => {
      announceRunSubmitted('preview-ready')
      trackRun({ id: 'preview-ready', kind: 'preview', status: 'running' })
    })
    await waitFor(() => {
      expect(FakeEventSource.find('preview-ready')).toBeTruthy()
    })
    act(() => {
      FakeEventSource.find('preview-ready')!.emit({
        job_id: 'preview-ready',
        stage: 'preview_ready',
        message: 'ready',
        current: 1,
        total: 1,
        extra: null,
      })
    })
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'good',
            message: t.toastPreviewDone('preview-ready'),
            href: '/jobs/preview-ready',
          }),
        ]),
      )
    })
  })

  it('toasts completion from poll refresh when SSE is silent', async () => {
    const intervals: Array<() => void> = []
    vi.spyOn(window, 'setInterval').mockImplementation((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        intervals.push(handler as () => void)
      }
      return 1 as unknown as number
    })
    vi.spyOn(window, 'clearInterval').mockImplementation(() => undefined)

    let status: 'running' | 'done' = 'running'
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0]
      if (path === '/api/jobs') {
        return jsonResponse({ jobs: [] })
      }
      if (path.endsWith('/api/jobs/preview-poll')) {
        return jsonResponse({
          id: 'preview-poll',
          status,
          type: 'preview',
          error: null,
          product_url: null,
          preview: null,
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(<RunToaster />)
    act(() => {
      announceRunSubmitted('preview-poll')
      trackRun({ id: 'preview-poll', kind: 'preview', status: 'running' })
    })
    await waitFor(() => expect(intervals.length).toBeGreaterThan(0))
    status = 'done'
    await act(async () => {
      intervals.forEach((tick) => tick())
    })
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'good',
            message: t.toastPreviewDone('preview-poll'),
            href: '/jobs/preview-poll',
          }),
        ]),
      )
    })
  })

  it('toasts cancellation from SSE when getJob fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/api/jobs/preview-gone')) {
        return jsonResponse({ detail: 'missing' }, 404)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(<RunToaster />)
    act(() => {
      announceRunSubmitted('preview-gone')
      trackRun({ id: 'preview-gone', kind: 'preview', status: 'running' })
    })
    await waitFor(() => {
      expect(FakeEventSource.find('preview-gone')).toBeTruthy()
    })
    act(() => {
      FakeEventSource.find('preview-gone')!.emit({
        job_id: 'preview-gone',
        stage: 'cancelled',
        message: 'stopped',
        current: 0,
        total: 0,
        extra: null,
      })
    })
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunCancelledJob('preview-gone'),
            href: '/jobs/preview-gone',
          }),
        ]),
      )
    })
  })
})
