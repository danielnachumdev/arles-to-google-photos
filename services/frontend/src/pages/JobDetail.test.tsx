import '@testing-library/jest-dom/vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job, JobChild, JobEvent, JobStatus } from '../api/types.ts'
import { affectedCancelJobLabel } from '../components/CancelJobDialog.tsx'
import { affectedRestartJobLabel } from '../components/RestartJobDialog.tsx'
import { GoogleAuthCancelledError, requestGooglePhotosAccessToken } from '../lib/googleAuth.ts'
import { formatJobDate } from '../lib/formatJobDate.ts'
import { jobStatusLabel, jobTypeLabel, t } from '../lib/language.ts'
import { FakeEventSource, JobEventBuilder, jsonResponse } from '../testing/index.ts'
import { JobDetail } from './JobDetail.tsx'

vi.mock('../lib/googleAuth.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/googleAuth.ts')>()
  return {
    ...actual,
    requestGooglePhotosAccessToken: vi.fn(),
  }
})

const JOB: Job = {
  id: 'job-summer',
  number: 42,
  status: 'done',
  type: 'upload',
  error: null,
  product_url: 'https://photos.example/summer',
  folder_label: 'Day1',
  created_at: '2012-08-02T10:00:00+00:00',
  finished_at: '2012-08-02T10:01:00+00:00',
  children: [],
  preview: {
    title: 'קיץ 2012',
    description: null,
    multi_index: false,
    journal: null,
    items: [
      {
        id: '20120802_01',
        relpath: 'hrimages/20120802_01hr.JPG',
        caption: 'יום ראשון',
        size_bytes: 12,
        last_modified: '2012-08-02T10:00:00',
        taken_on: '2012-08-02',
      },
      {
        id: '20120802_02',
        relpath: 'hrimages/20120802_02hr.JPG',
        caption: 'יום שני',
        size_bytes: 14,
        last_modified: '2012-08-02T11:00:00',
        taken_on: '2012-08-02',
      },
    ],
  },
}

const HISTORY: JobEvent[] = [
  JobEventBuilder.ingest().build(),
  JobEventBuilder.previewReady().build(),
]

describe('JobDetail', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    FakeEventSource.install()
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: HISTORY })
      }
      if (url.includes('/api/jobs/job-summer')) {
        return jsonResponse(JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(requestGooglePhotosAccessToken).mockReset()
  })

  afterEach(() => {
    document.title = t.documentTitle
    vi.useRealTimers()
    vi.unstubAllGlobals()
    FakeEventSource.install()
    vi.restoreAllMocks()
  })

  it('shows status, metadata, and run history without the album editor', async () => {
    render(
      <MemoryRouter>
        <JobDetail jobId="job-summer" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: t.jobDetailHeading })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: t.runHistoryHeading })).toBeInTheDocument()
    expect(screen.getByText(jobTypeLabel('upload'))).toBeInTheDocument()
    const doneStatus = screen.getByText(jobStatusLabel('done'))
    expect(doneStatus).toHaveClass('job-list__status', 'job-list__status--done')
    expect(doneStatus).not.toHaveAttribute('aria-busy')
    expect(screen.getByText(t.titleLabel)).toBeInTheDocument()
    expect(screen.queryByText(t.jobPreviewSummary)).not.toBeInTheDocument()
    expect(screen.queryByText(t.jobUrlLabel)).not.toBeInTheDocument()
    expect(screen.queryByText(t.jobHeadersLabel)).not.toBeInTheDocument()
    expect(screen.queryByText('done')).not.toBeInTheDocument()
    expect(screen.getByText('job-summer')).toBeInTheDocument()
    expect(screen.getByText(t.jobNumberLabel)).toBeInTheDocument()
    const numberRow = screen.getByText(t.jobNumberLabel).closest('.job-detail__row')
    expect(numberRow).toHaveTextContent('42')
    expect(screen.getByText('Day1')).toBeInTheDocument()
    expect(screen.getByText('Writing upload')).toBeInTheDocument()
    expect(screen.getAllByText('קיץ 2012').length).toBeGreaterThan(0)
    expect(screen.getByText('0/1')).toBeInTheDocument()
    expect(screen.queryByText('ingest')).not.toBeInTheDocument()
    expect(screen.queryByText('preview_ready')).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: t.technicalLogs })).toBeInTheDocument()
    expect(screen.queryByLabelText(t.titleLabel)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.save })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openAlbum })).toHaveAttribute(
      'href',
      '/albums/job-summer',
    )
    expect(screen.getByText(t.photosHeading)).toBeInTheDocument()
    expect(screen.getByText(t.historyPhotoCount(2))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openPhotosAlbum })).toHaveAttribute(
      'href',
      'https://photos.example/summer',
    )
    expect(screen.getByText(t.jobFinishedLabel)).toBeInTheDocument()
    expect(screen.getByText(formatJobDate('2012-08-02T10:01:00+00:00'))).toBeInTheDocument()
    expect(FakeEventSource.instances[0]?.url).toBe('/api/jobs/job-summer/events?phase=history')
  })

  it('shows unsupported Arles copy for a failed scrape job', async () => {
    const url = 'https://albums.example/album/index2012.html'
    const failed: Job = {
      id: 'scrape-unsupported',
      number: 9,
      status: 'failed',
      type: 'scrape',
      error: `Not a supported Arles album: ${url}`,
      error_code: 'not_arles',
      product_url: null,
      preview: null,
      scrape_url: url,
      created_at: '2026-08-08T10:00:00+00:00',
      finished_at: '2026-08-08T10:00:04+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const requestUrl = String(input)
      if (requestUrl.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (requestUrl.includes('/api/jobs/scrape-unsupported')) {
        return jsonResponse(failed)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-unsupported" />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.jobErrorHeading)).toBeInTheDocument()
    expect(screen.getByText(t.errorScrapeUnsupported(url))).toBeInTheDocument()
    expect(screen.getByText(jobStatusLabel('failed'))).toBeInTheDocument()
    expect(screen.queryByText('Check the URL and headers')).not.toBeInTheDocument()
    expect(screen.getByText(url)).toBeInTheDocument()
  })

  it('shows Finished for failed and cancelled jobs when finished_at is set', async () => {
    const failed: Job = {
      id: 'job-failed',
      status: 'failed',
      type: 'preview',
      error: 'parse failed',
      product_url: null,
      preview: null,
      created_at: '2026-08-08T10:00:00+00:00',
      finished_at: '2026-08-08T10:02:00+00:00',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-failed')) {
        return jsonResponse(failed)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    const { rerender } = render(
      <MemoryRouter>
        <JobDetail jobId="job-failed" />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.jobFinishedLabel)).toBeInTheDocument()
    expect(screen.getByText(formatJobDate('2026-08-08T10:02:00+00:00'))).toBeInTheDocument()

    const cancelled: Job = {
      ...failed,
      id: 'job-cancelled',
      status: 'cancelled',
      error: null,
      finished_at: '2026-08-08T10:03:00+00:00',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-cancelled')) {
        return jsonResponse(cancelled)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    rerender(
      <MemoryRouter>
        <JobDetail jobId="job-cancelled" />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.jobFinishedLabel)).toBeInTheDocument()
    expect(screen.getByText(formatJobDate('2026-08-08T10:03:00+00:00'))).toBeInTheDocument()
  })

  it('shows preview photo count without Photos URL until published', async () => {
    const previewJob: Job = {
      id: 'preview-only',
      status: 'done',
      type: 'preview',
      error: null,
      product_url: null,
      folder_label: 'Day1',
      preview: {
        title: 'Day 1',
        description: null,
        multi_index: false,
        journal: null,
        items: [
          {
            id: '20120802_01',
            relpath: 'hrimages/20120802_01hr.JPG',
            caption: 'one',
            size_bytes: 12,
            last_modified: null,
            taken_on: '2012-08-02',
          },
        ],
      },
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/preview-only')) {
        return jsonResponse(previewJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="preview-only" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('preview-only')).toBeInTheDocument()
    expect(screen.getByText(t.photosHeading)).toBeInTheDocument()
    expect(screen.getByText(t.historyPhotoCount(1))).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openPhotosAlbum })).not.toBeInTheDocument()
  })

  it('shows Photos URL on preview after a prior publish', async () => {
    const previewJob: Job = {
      id: 'preview-published',
      status: 'done',
      type: 'preview',
      error: null,
      product_url: 'https://photos.example/republish',
      folder_label: 'Day1',
      preview: {
        title: 'Day 1',
        description: null,
        multi_index: false,
        journal: null,
        items: [
          {
            id: '20120802_01',
            relpath: 'hrimages/20120802_01hr.JPG',
            caption: 'one',
            size_bytes: 12,
            last_modified: null,
            taken_on: '2012-08-02',
          },
        ],
      },
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/preview-published')) {
        return jsonResponse(previewJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="preview-published" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('preview-published')).toBeInTheDocument()
    expect(screen.getByText(t.historyPhotoCount(1))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openPhotosAlbum })).toHaveAttribute(
      'href',
      'https://photos.example/republish',
    )
  })

  it('appends live SSE events to the timeline', async () => {
    render(
      <MemoryRouter>
        <JobDetail jobId="job-summer" />
      </MemoryRouter>,
    )

    await screen.findByText('Writing upload')
    FakeEventSource.instances[0]!.emit(
      JSON.stringify({
        job_id: 'job-summer',
        stage: 'publish',
        message: 'Starting upload',
        current: 0,
        total: 3,
        extra: null,
        occurred_at: '2012-08-02T10:02:00+00:00',
      }),
    )

    expect(await screen.findByText('Starting upload')).toBeInTheDocument()
    expect(screen.queryByText('publish')).not.toBeInTheDocument()
    expect(screen.getByText('0/3')).toBeInTheDocument()
  })

  it('hides ops lines until technical logs are enabled', async () => {
    const history: JobEvent[] = [
      ...HISTORY,
      {
        job_id: 'job-summer',
        stage: 'scrape',
        message: 'Saved hrimages/20120802_01hr.JPG · 1/2 · 12KB',
        current: 1,
        total: 2,
        extra: null,
        occurred_at: '2012-08-02T10:02:30+00:00',
        kind: 'log',
        audience: 'ui',
      },
      {
        job_id: 'job-summer',
        stage: 'scrape',
        message: 'Fetching image page 20120802_01: https://albums.example/imagepages/20120802_01.html',
        current: 1,
        total: 2,
        extra: null,
        occurred_at: '2012-08-02T10:02:31+00:00',
        kind: 'log',
        audience: 'ops',
      },
      {
        job_id: 'job-summer',
        stage: 'scrape',
        message: 'GET https://albums.example/index.html → 200, 812KB',
        current: 0,
        total: 0,
        extra: null,
        occurred_at: '2012-08-02T10:03:00+00:00',
        kind: 'log',
        audience: 'ops',
      },
    ]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: history })
      }
      if (url.includes('/api/jobs/job-summer')) {
        return jsonResponse(JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="job-summer" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Writing upload')).toBeInTheDocument()
    expect(screen.getByText(/Saved hrimages\/20120802_01hr.JPG/)).toBeInTheDocument()
    expect(screen.queryByText(/812KB/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Fetching image page/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: t.technicalLogs }))
    expect(screen.getByText(/812KB/)).toBeInTheDocument()
    expect(screen.getByText(/Fetching image page/)).toBeInTheDocument()
    expect(screen.queryByText('scrape')).not.toBeInTheDocument()
  })

  it('shows scrape fields, parent, preview summary, and child job links', async () => {
    const childPreview: JobChild = {
      id: 'preview-day1',
      number: 13,
      status: 'done',
      type: 'preview',
      title: 'Day 1',
      preview: {
        title: 'Day 1',
        description: null,
        multi_index: false,
        journal: null,
        items: [],
      },
    }
    const childUpload: JobChild = {
      id: 'upload-day1',
      number: 14,
      status: 'pending',
      type: 'upload',
    }
    const scrapeJob: Job = {
      id: 'scrape-root',
      number: 11,
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      preview_job_id: 'preview-day1',
      url: 'https://gallery.example/index.html',
      parent_job_id: 'scrape-parent',
      created_at: '2026-08-08T10:00:00+00:00',
      updated_at: '2026-08-08T10:05:00+00:00',
      headers: { Authorization: '***' },
      auto_publish: true,
      children: [childPreview, childUpload],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/scrape-root')) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-root" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('scrape-root')).toBeInTheDocument()
    expect(screen.getByText(t.jobNumberLabel)).toBeInTheDocument()
    expect(screen.getByText(t.jobNumberLabel).closest('.job-detail__row')).toHaveTextContent('11')
    expect(screen.getByText(jobTypeLabel('scrape'))).toBeInTheDocument()
    const runningStatus = screen.getByText(jobStatusLabel('running'))
    expect(runningStatus).toHaveClass('job-list__status', 'job-list__status--running')
    expect(runningStatus).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('link', { name: 'https://gallery.example/index.html' })).toHaveAttribute(
      'href',
      'https://gallery.example/index.html',
    )
    expect(screen.getByRole('link', { name: 'scrape-parent' })).toHaveAttribute(
      'href',
      '/jobs/scrape-parent',
    )
    expect(screen.getByText(t.jobHeadersLabel)).toBeInTheDocument()
    expect(screen.getByText(/Authorization/)).toBeInTheDocument()
    expect(screen.queryByText(t.jobFolderLabel)).not.toBeInTheDocument()
    expect(screen.queryByText(t.titleLabel)).not.toBeInTheDocument()
    expect(screen.queryByText(t.jobPreviewSummary)).not.toBeInTheDocument()
    expect(screen.queryByText(t.photosHeading)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openPhotosAlbum })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: t.jobChildrenHeading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('Day 1') })).toHaveAttribute(
      'href',
      '/jobs/preview-day1',
    )
    expect(screen.getByRole('link', { name: t.jobsOpenAria('upload-day1') })).toHaveAttribute(
      'href',
      '/jobs/upload-day1',
    )
    const previewChild = screen.getByRole('link', { name: t.jobsOpenAria('Day 1') }).closest('li')
    const uploadChild = screen.getByRole('link', { name: t.jobsOpenAria('upload-day1') }).closest('li')
    expect(previewChild).toHaveTextContent('13')
    expect(uploadChild).toHaveTextContent('14')
    const fields = screen.getByText(t.jobIdLabel).closest('dl') as HTMLElement
    expect(within(fields).queryByRole('link', { name: t.openAlbum })).toBeNull()
    expect(screen.getByRole('link', { name: t.openAlbum })).toHaveAttribute(
      'href',
      '/albums/preview-day1',
    )
    expect(screen.getByText(t.jobAutoPublishLabel)).toBeInTheDocument()
    expect(screen.getByText(jobTypeLabel('preview'))).toBeInTheDocument()
    expect(screen.getByText(jobTypeLabel('upload'))).toBeInTheDocument()
    expect(screen.getByText(jobStatusLabel('done'))).toHaveClass(
      'job-list__status',
      'job-list__status--done',
    )
    expect(screen.getByText(jobStatusLabel('pending'))).toHaveClass(
      'job-list__status',
      'job-list__status--pending',
    )
  })

  it('pulsates child running status with the same overview colors', async () => {
    const scrapeJob: Job = {
      id: 'scrape-status',
      status: 'failed',
      type: 'scrape',
      error: 'blocked',
      product_url: null,
      preview: null,
      created_at: '2026-08-08T10:00:00+00:00',
      children: [
        { id: 'child-done', status: 'done', type: 'preview', title: 'Done child' },
        { id: 'child-failed', status: 'failed', type: 'upload', title: 'Failed child' },
        { id: 'child-pending', status: 'pending', type: 'upload', title: 'Pending child' },
        { id: 'child-running', status: 'running', type: 'preview', title: 'Running child' },
      ],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/scrape-status')) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-status" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('scrape-status')).toBeInTheDocument()

    const statusRow = screen.getByText(t.jobStatusHeading).closest('.job-detail__row')
    expect(statusRow).toBeTruthy()
    const jobStatus = within(statusRow as HTMLElement).getByText(jobStatusLabel('failed'))
    expect(jobStatus).toHaveClass('job-list__status', 'job-list__status--failed')
    expect(jobStatus).not.toHaveAttribute('aria-busy')

    function childStatus(title: string, status: JobStatus): HTMLElement {
      const row = screen.getByRole('link', { name: t.jobsOpenAria(title) }).closest('li') as HTMLElement
      return within(row).getByText(jobStatusLabel(status))
    }

    expect(childStatus('Done child', 'done')).toHaveClass('job-list__status', 'job-list__status--done')
    expect(childStatus('Failed child', 'failed')).toHaveClass(
      'job-list__status',
      'job-list__status--failed',
    )
    expect(childStatus('Pending child', 'pending')).toHaveClass(
      'job-list__status',
      'job-list__status--pending',
    )
    const runningChild = childStatus('Running child', 'running')
    expect(runningChild).toHaveClass('job-list__status', 'job-list__status--running')
    expect(runningChild).toHaveAttribute('aria-busy', 'true')
  })

  it('links to a running preview child before preview is ready', async () => {
    const childId = 'preview-early-1'
    const scrapeJob: Job = {
      id: 'scrape-early',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      folder_label: 'albums.example',
      url: 'https://albums.example/day1',
      child_ids: [childId],
      children: [
        {
          id: childId,
          status: 'running',
          type: 'preview',
          folder_label: 'albums.example',
          preview: null,
          parent_job_id: 'scrape-early',
        },
      ],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/scrape-early')) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-early" />
      </MemoryRouter>,
    )

    const openChild = await screen.findByRole('link', {
      name: t.jobsOpenAria(childId),
    })
    expect(openChild).toHaveAttribute('href', `/jobs/${childId}`)
    expect(screen.queryByText(t.jobFolderLabel)).not.toBeInTheDocument()
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()
    const row = openChild.closest('li') as HTMLElement
    const runningChild = within(row).getByText(jobStatusLabel('running'))
    expect(runningChild).toHaveClass('job-list__status', 'job-list__status--running')
    expect(runningChild).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText(jobTypeLabel('preview'))).toBeInTheDocument()
    expect(within(row).queryByRole('link', { name: t.openAlbum })).toBeNull()
  })

  it('grows hub children after a child SSE event even if embedded children are stale', async () => {
    const dummy: JobChild = {
      id: 'preview-dummy',
      status: 'pending',
      type: 'preview',
    }
    const day1: JobChild = {
      id: 'scrape-day1',
      number: 2,
      status: 'pending',
      type: 'scrape',
    }
    const day2: JobChild = {
      id: 'scrape-day2',
      number: 3,
      status: 'pending',
      type: 'scrape',
    }
    let hub: Job = {
      id: 'hub-spawn',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub/',
      created_at: '2026-08-08T10:00:00+00:00',
      child_ids: [dummy.id],
      children: [dummy],
    }
    let listedChildren: JobChild[] = [dummy]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({ jobs: listedChildren })
      }
      if (url.includes('/api/jobs/hub-spawn')) {
        return jsonResponse(hub)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="hub-spawn" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria(dummy.id) })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.jobsOpenAria(day1.id) })).not.toBeInTheDocument()

    hub = {
      ...hub,
      status: 'waiting',
      child_ids: [dummy.id, day1.id, day2.id],
      children: [dummy],
    }
    listedChildren = [day1, day2]
    act(() => {
      FakeEventSource.instances[0]!.emit({
        job_id: hub.id,
        stage: 'child',
        message: day1.id,
        current: 0,
        total: 0,
        extra: { child_id: day1.id, type: 'scrape' },
        occurred_at: '2026-08-08T10:01:00+00:00',
      })
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria(day1.id) })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria(day2.id) })).toBeInTheDocument()
  })

  it('grows hub children on poll while the parent is waiting', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const dummy: JobChild = {
      id: 'preview-dummy',
      status: 'pending',
      type: 'preview',
    }
    const day1: JobChild = {
      id: 'scrape-day1',
      number: 2,
      status: 'pending',
      type: 'scrape',
    }
    let hub: Job = {
      id: 'hub-wait',
      status: 'waiting',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub/',
      created_at: '2026-08-08T10:00:00+00:00',
      child_ids: [dummy.id],
    }
    let listedChildren: JobChild[] = [dummy]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({ jobs: listedChildren })
      }
      if (url.includes('/api/jobs/hub-wait')) {
        return jsonResponse(hub)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="hub-wait" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria(dummy.id) })).toBeInTheDocument()

    hub = { ...hub, child_ids: [day1.id] }
    listedChildren = [day1]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria(day1.id) })).toBeInTheDocument()
  })

  it('loads children from /children when they are not embedded', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({
          children: [
            {
              id: 'child-from-api',
              status: 'pending',
              type: 'preview',
              title: 'Nested',
              preview: {
                title: 'Nested',
                description: null,
                multi_index: false,
                journal: null,
                items: [],
              },
            },
          ],
        })
      }
      if (url.includes('/api/jobs/scrape-bare')) {
        return jsonResponse({
          id: 'scrape-bare',
          status: 'done',
          type: 'scrape',
          error: null,
          product_url: null,
          preview: null,
          preview_job_id: 'child-from-api',
          url: 'https://gallery.example/bare/',
        } satisfies Job)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-bare" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('Nested') })).toHaveAttribute(
      'href',
      '/jobs/child-from-api',
    )
    const albumLinks = screen.getAllByRole('link', { name: t.openAlbum })
    expect(albumLinks.map((link) => link.getAttribute('href'))).toEqual([
      '/albums/child-from-api',
      '/albums/child-from-api',
    ])
  })

  it('links a done scrape job to the preview child album desk', async () => {
    const scrapeJob: Job = {
      id: 'scrape-done',
      status: 'done',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      preview_job_id: 'preview-day1',
      url: 'https://gallery.example/done/',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [
        {
          id: 'preview-day1',
          status: 'done',
          type: 'preview',
          title: 'Day 1',
          preview: {
            title: 'Day 1',
            description: null,
            multi_index: false,
            journal: null,
            items: [],
          },
        },
        { id: 'scrape-nested', status: 'done', type: 'scrape', title: 'Nested scrape' },
      ],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/scrape-done')) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-done" />
      </MemoryRouter>,
    )

    expect(await screen.findByText('scrape-done')).toBeInTheDocument()
    const fields = screen.getByText(t.jobIdLabel).closest('dl') as HTMLElement
    expect(within(fields).getByRole('link', { name: t.openAlbum })).toHaveAttribute(
      'href',
      '/albums/preview-day1',
    )
    const childRow = screen.getByRole('link', { name: t.jobsOpenAria('Day 1') }).closest('li') as HTMLElement
    expect(within(childRow).getByRole('link', { name: t.openAlbum })).toHaveAttribute(
      'href',
      '/albums/preview-day1',
    )
    expect(
      screen
        .getAllByRole('link', { name: t.openAlbum })
        .every((link) => link.getAttribute('href') !== '/albums/scrape-done'),
    ).toBe(true)
  })

  it('links a done folder hub parent to the first leaf album desk', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({
          children: [
            {
              id: 'leaf-aug10',
              status: 'done',
              type: 'preview',
              title: 'Aug10',
              preview: {
                title: 'Aug10',
                description: null,
                multi_index: false,
                journal: null,
                items: [],
              },
            },
          ],
        })
      }
      if (url.includes('/api/jobs/hub-parent')) {
        return jsonResponse({
          id: 'hub-parent',
          status: 'done',
          type: 'preview',
          error: null,
          product_url: null,
          preview: null,
          preview_job_id: 'leaf-aug10',
          folder_label: 'Italy2012',
        } satisfies Job)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="hub-parent" />
      </MemoryRouter>,
    )

    const albumLinks = await screen.findAllByRole('link', { name: t.openAlbum })
    expect(albumLinks.map((link) => link.getAttribute('href'))).toEqual([
      '/albums/leaf-aug10',
      '/albums/leaf-aug10',
    ])
  })

  it('shows cancel while pending, running, or waiting and posts cancel', async () => {
    const running: Job = {
      id: 'job-run',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      url: 'https://gallery.example/run/',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    const cancelled: Job = { ...running, status: 'cancelled' }
    let current: Job = running
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        current = cancelled
        return jsonResponse(current)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-run')) {
        return jsonResponse(current)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="job-run" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: t.cancelJob })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: t.cancelJob }))
    fireEvent.click(screen.getByRole('button', { name: t.confirmCancelJobYes }))

    await waitFor(() => {
      expect(screen.getByText(jobStatusLabel('cancelled'))).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: t.cancelJob })).not.toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        (call) => String(call[0]).endsWith('/api/jobs/job-run/cancel') && (call[1] as RequestInit)?.method === 'POST',
      ),
    ).toBe(true)
  })

  it('lists cancellable child links in the cancel modal and posts cancel once', async () => {
    const running: Job = {
      id: 'hub-run',
      number: 1,
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      url: 'https://albums.example/hub/',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [
        {
          id: 'child-scrape',
          number: 2,
          status: 'pending',
          type: 'scrape',
          scrape_url: 'https://albums.example/day1',
        },
      ],
    }
    const cancelled: Job = { ...running, status: 'cancelled' }
    let current: Job = running
    const previewChild = {
      id: 'child-preview',
      number: 3,
      status: 'running' as const,
      type: 'preview' as const,
      title: 'Day 1',
      parent_job_id: 'child-scrape',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({
          descendants: [running.children![0], previewChild],
        })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        current = cancelled
        return jsonResponse(current)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/hub-run')) {
        return jsonResponse(current)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="hub-run" />
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    expect(await screen.findByText(t.confirmCancelJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmCancelJobBody)).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(
          affectedCancelJobLabel({
            id: 'child-scrape',
            number: 2,
            type: 'scrape',
            scrape_url: 'https://albums.example/day1',
          }),
        ),
      }),
    ).toHaveAttribute('href', '/jobs/child-scrape')
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedCancelJobLabel(previewChild)),
      }),
    ).toHaveAttribute('href', '/jobs/child-preview')

    fireEvent.click(screen.getByRole('button', { name: t.confirmCancelJobYes }))
    await waitFor(() => {
      expect(screen.getByText(jobStatusLabel('cancelled'))).toBeInTheDocument()
    })
    const cancelPosts = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).endsWith('/api/jobs/hub-run/cancel') && (call[1] as RequestInit)?.method === 'POST',
    )
    expect(cancelPosts).toHaveLength(1)
  })

  it('keeps the simple cancel copy when the job has no cancellable children', async () => {
    const running: Job = {
      id: 'job-solo',
      status: 'running',
      type: 'preview',
      error: null,
      product_url: null,
      preview: null,
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-solo')) {
        return jsonResponse(running)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="job-solo" />
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    expect(await screen.findByText(t.confirmCancelJobBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmCancelJobWithChildrenBody)).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows ETA from event extra on scrape download logs', async () => {
    const scrapeJob: Job = {
      id: 'scrape-eta',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      url: 'https://gallery.example/eta/',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    const history: JobEvent[] = [
      {
        job_id: 'scrape-eta',
        stage: 'scrape',
        message: 'Saved hrimages/20120802_01hr.JPG · 1/16 · 640 KB',
        current: 1,
        total: 16,
        extra: { item_bytes: 655360, bytes_done: 655360 },
        occurred_at: '2026-08-08T10:00:01+00:00',
      },
      {
        job_id: 'scrape-eta',
        stage: 'scrape',
        message: 'Saved hrimages/20120802_02hr.JPG · 2/16 · 812 KB · ~1m 20s left',
        current: 2,
        total: 16,
        extra: { eta_seconds: 80, item_bytes: 831488, bytes_done: 1486848, rate_bps: 12000 },
        occurred_at: '2026-08-08T10:00:08+00:00',
      },
    ]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: history })
      }
      if (url.includes('/api/jobs/scrape-eta')) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="scrape-eta" />
      </MemoryRouter>,
    )

    expect(
      await screen.findByText('Saved hrimages/20120802_02hr.JPG · 2/16 · 812 KB · ~1m 20s left'),
    ).toBeInTheDocument()
    expect(screen.getAllByText(/^\d+\/16$/).map((node) => node.textContent)).toEqual(['1/16', '2/16'])
    expect(document.querySelector('.job-detail__eta')).toHaveTextContent(t.etaLeft(80))
    expect(document.querySelectorAll('.job-detail__eta')).toHaveLength(1)
  })

  it('hides cancel on a finished job', async () => {
    render(
      <MemoryRouter>
        <JobDetail jobId="job-summer" />
      </MemoryRouter>,
    )

    await screen.findByText(jobStatusLabel('done'))
    expect(screen.queryByRole('button', { name: t.cancelJob })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.restartJob })).not.toBeInTheDocument()
  })

  it('shows Waiting with Cancel, no Restart, and warnings', async () => {
    const waiting: Job = {
      id: 'job-waiting',
      status: 'waiting',
      type: 'scrape',
      error: null,
      warnings: ['Child #12 failed: site down'],
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-waiting')) {
        return jsonResponse(waiting)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="job-waiting" />
      </MemoryRouter>,
    )

    expect(await screen.findByText(jobStatusLabel('waiting'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.cancelJob })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.restartJob })).not.toBeInTheDocument()
    expect(screen.getByText(t.jobWarningsHeading)).toBeInTheDocument()
    expect(screen.getByText('Child #12 failed: site down')).toBeInTheDocument()
  })

  it('shows restart only when cancelled and navigates to the new job', async () => {
    const cancelled: Job = {
      id: 'job-cancelled',
      number: 12,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/day1',
      created_at: '2026-08-08T10:00:00+00:00',
      finished_at: '2026-08-08T10:01:00+00:00',
      children: [],
    }
    const created: Job = {
      id: 'job-new',
      number: 13,
      status: 'pending',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/day1',
      created_at: '2026-08-08T12:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/restart') && init?.method === 'POST') {
        return jsonResponse(created, 201)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-new')) {
        return jsonResponse(created)
      }
      if (url.includes('/api/jobs/job-cancelled')) {
        return jsonResponse(cancelled)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    function JobDetailPage() {
      const { jobId } = useParams()
      return <JobDetail jobId={jobId ?? ''} />
    }

    render(
      <MemoryRouter initialEntries={['/jobs/job-cancelled']}>
        <Routes>
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: t.restartJob })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: t.restartJob }))
    expect(screen.getByRole('dialog')).toHaveTextContent(t.confirmRestartJobBody)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))

    await waitFor(() => {
      expect(screen.getByText('job-new')).toBeInTheDocument()
    })
    expect(
      fetchMock.mock.calls.some(
        (call) =>
          String(call[0]).endsWith('/api/jobs/job-cancelled/restart') &&
          (call[1] as RequestInit)?.method === 'POST',
      ),
    ).toBe(true)
    const restartPost = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).endsWith('/api/jobs/job-cancelled/restart') &&
        (call[1] as RequestInit)?.method === 'POST',
    )
    expect(JSON.parse(String((restartPost?.[1] as RequestInit)?.body))).toEqual({})
    expect(screen.queryByRole('button', { name: t.restartJob })).not.toBeInTheDocument()
  })

  it('asks all vs remaining when restarting a cancelled hub with scrape children', async () => {
    const cancelled: Job = {
      id: 'hub-run',
      number: 4,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub',
      created_at: '2026-08-08T10:00:00+00:00',
      finished_at: '2026-08-08T10:01:00+00:00',
      children: [],
    }
    const remainingChild = {
      id: 'child-failed',
      number: 6,
      status: 'failed' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day2',
    }
    const doneChild = {
      id: 'child-done',
      number: 5,
      status: 'done' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day1',
    }
    const created: Job = {
      id: 'hub-new',
      number: 7,
      status: 'pending',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub',
      created_at: '2026-08-08T12:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/restart-preview')) {
        return jsonResponse({
          descendants: [doneChild, remainingChild],
          done: [doneChild],
          remaining: [remainingChild],
        })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        return jsonResponse(created, 201)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/hub-new')) {
        return jsonResponse(created)
      }
      if (url.includes('/api/jobs/hub-run')) {
        return jsonResponse(cancelled)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    function JobDetailPage() {
      const { jobId } = useParams()
      return <JobDetail jobId={jobId ?? ''} />
    }

    render(
      <MemoryRouter initialEntries={['/jobs/hub-run']}>
        <Routes>
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: t.restartJob }))
    expect(await screen.findByText(t.confirmRestartJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmRestartJobBody)).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedRestartJobLabel(remainingChild)),
      }),
    ).toHaveAttribute('href', '/jobs/child-failed')
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedRestartJobLabel(doneChild)),
      }),
    ).toHaveAttribute('href', '/jobs/child-done')

    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobRemaining }))
    await waitFor(() => {
      expect(screen.getByText('hub-new')).toBeInTheDocument()
    })
    const restartPost = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).endsWith('/api/jobs/hub-run/restart') &&
        (call[1] as RequestInit)?.method === 'POST',
    )
    expect(JSON.parse(String((restartPost?.[1] as RequestInit)?.body))).toEqual({ mode: 'remaining' })
  })

  it('shows the not-found page when the job is missing', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'job not found' }, 404))
    render(
      <MemoryRouter>
        <JobDetail jobId="nope" />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: t.notFoundHeading })).toBeInTheDocument()
    expect(screen.getByText(t.notFoundLede)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows empty run history copy', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-summer')) {
        return jsonResponse(JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId="job-summer" />
      </MemoryRouter>,
    )
    expect(await screen.findByText(t.runHistoryEmpty)).toBeInTheDocument()
  })

  it('parses ETA seconds from a string extra field', async () => {
    const scrapeJob: Job = {
      id: 'scrape-eta-str',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      url: 'https://gallery.example/eta/',
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({
          events: [
            {
              job_id: scrapeJob.id,
              stage: 'scrape',
              message: 'Saved file',
              current: 2,
              total: 8,
              extra: { eta_seconds: '45' },
              occurred_at: '2026-08-08T10:00:08+00:00',
            },
          ],
        })
      }
      if (url.includes(`/api/jobs/${scrapeJob.id}`)) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId={scrapeJob.id} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Saved file')).toBeInTheDocument()
    expect(document.querySelector('.job-detail__eta')).toHaveTextContent(t.etaLeft(45))
  })

  it('lists header names without values and a non-http scrape url as text', async () => {
    const scrapeJob: Job = {
      id: 'scrape-headers',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'albums.example/day1',
      header_names: ['Cookie'],
      created_at: '2026-08-08T10:00:00+00:00',
      children: [],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes(`/api/jobs/${scrapeJob.id}`)) {
        return jsonResponse(scrapeJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId={scrapeJob.id} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Cookie')).toBeInTheDocument()
    expect(screen.getByText('albums.example/day1')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'albums.example/day1' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openAlbum })).not.toBeInTheDocument()
  })

  it('falls back to child_ids when /children fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({ detail: 'down' }, 500)
      }
      if (url.includes('/api/jobs/job-ids-only')) {
        return jsonResponse({
          ...JOB,
          id: 'job-ids-only',
          type: 'scrape',
          status: 'done',
          preview: null,
          product_url: null,
          children: [],
          child_ids: ['child-a'],
          scrape_url: 'https://albums.example/hub',
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId="job-ids-only" />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: t.jobsOpenAria('child-a') })).toHaveAttribute(
      'href',
      '/jobs/child-a',
    )
  })

  it('refetches children after a cancel 409', async () => {
    const dummy: JobChild = {
      id: 'preview-dummy',
      status: 'pending',
      type: 'preview',
    }
    const day1: JobChild = {
      id: 'scrape-day1',
      number: 2,
      status: 'pending',
      type: 'scrape',
    }
    let hub: Job = {
      id: 'hub-cancel-stale',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      scrape_url: 'https://albums.example/hub/',
      created_at: '2026-08-08T10:00:00+00:00',
      child_ids: [dummy.id],
      children: [dummy],
    }
    let listedChildren: JobChild[] = [dummy]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        hub = {
          ...hub,
          status: 'waiting',
          child_ids: [day1.id],
          children: undefined,
        }
        listedChildren = [day1]
        return jsonResponse({ detail: 'job already finished' }, 409)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.endsWith('/children')) {
        return jsonResponse({ jobs: listedChildren })
      }
      if (url.includes('/api/jobs/hub-cancel-stale')) {
        return jsonResponse(hub)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobDetail jobId="hub-cancel-stale" />
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmCancelJobYes }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorCancel('HTTP 409: job already finished'),
    )
    expect(await screen.findByRole('link', { name: t.jobsOpenAria(day1.id) })).toBeInTheDocument()
  })

  it('shows a cancel error when cancel fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        return jsonResponse({ detail: 'too late' }, 409)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-queued')) {
        return jsonResponse({
          id: 'job-queued',
          status: 'pending',
          type: 'preview',
          error: null,
          product_url: null,
          preview: null,
          created_at: '2026-08-01T00:00:00+00:00',
          children: [],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId="job-queued" />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmCancelJobYes }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorCancel('HTTP 409: too late'),
    )
  })

  it('keeps the cancelled upload when Google sign-in is cancelled on restart', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new GoogleAuthCancelledError())
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/restart') && init?.method === 'POST') {
        throw new Error('restart should not run after GIS cancel')
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-upload-cancelled')) {
        return jsonResponse({
          ...JOB,
          id: 'job-upload-cancelled',
          status: 'cancelled',
          finished_at: '2012-08-02T10:01:00+00:00',
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId="job-upload-cancelled" />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: t.restartJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))
    await waitFor(() => {
      expect(requestGooglePhotosAccessToken).toHaveBeenCalled()
    })
    expect(screen.getByText('job-upload-cancelled')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a restart error when restart fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/restart') && init?.method === 'POST') {
        return jsonResponse({ detail: 'busy' }, 409)
      }
      if (url.includes('/history')) {
        return jsonResponse({ events: [] })
      }
      if (url.includes('/api/jobs/job-cancelled')) {
        return jsonResponse({
          id: 'job-cancelled',
          number: 12,
          status: 'cancelled',
          type: 'scrape',
          error: null,
          product_url: null,
          preview: null,
          scrape_url: 'https://albums.example/day1',
          created_at: '2026-08-08T10:00:00+00:00',
          finished_at: '2026-08-08T10:01:00+00:00',
          children: [],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobDetail jobId="job-cancelled" />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: t.restartJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorRestart('HTTP 409: busy'),
    )
  })
})
