import '@testing-library/jest-dom/vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job, JobSummary } from '../api/types.ts'
import { affectedCancelJobLabel } from '../components/CancelJobDialog.tsx'
import { affectedRestartJobLabel } from '../components/RestartJobDialog.tsx'
import { GoogleAuthCancelledError, requestGooglePhotosAccessToken } from '../lib/googleAuth.ts'
import { formatJobDate } from '../lib/formatJobDate.ts'
import { jobStatusLabel, jobTypeLabel, t } from '../lib/language.ts'
import { clearTrackedRuns, trackRun } from '../lib/runTracker.ts'
import { ConfirmDialogInteractor, FakeEventSource, jsonResponse } from '../testing/index.ts'
import { JobList, JOB_LIST_POLL_MS, JOB_LIST_SCRAPE_POLL_MS } from './JobList.tsx'

vi.mock('../lib/googleAuth.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/googleAuth.ts')>()
  return {
    ...actual,
    requestGooglePhotosAccessToken: vi.fn(),
  }
})

const JOBS: JobSummary[] = [
  {
    id: 'job-summer',
    number: 42,
    status: 'done',
    type: 'upload',
    error: null,
    title: 'קיץ 2012',
    item_count: 3,
    created_at: '2012-08-02T10:00:00+00:00',
    finished_at: '2012-08-02T10:00:45+00:00',
    product_url: 'https://photos.example/summer',
    folder_label: 'Day1',
    duration_seconds: 45,
    last_stage: 'done',
  },
  {
    id: 'job-winter',
    number: 77,
    status: 'done',
    type: 'preview',
    error: null,
    title: 'חורף 2019',
    item_count: 1,
    created_at: '2019-01-15T00:00:00+00:00',
    finished_at: '2019-01-15T00:00:12+00:00',
    product_url: null,
    folder_label: 'SkiTrip',
    duration_seconds: 12,
    last_stage: 'done',
  },
  {
    id: 'job-broken',
    number: 3,
    status: 'failed',
    type: 'preview',
    error: 'parse failed',
    title: null,
    item_count: 0,
    created_at: '2020-01-01T00:00:00+00:00',
    finished_at: '2020-01-01T00:00:05+00:00',
    product_url: null,
    folder_label: 'Broken',
    last_stage: 'failed',
  },
  {
    id: 'job-queued',
    number: 20,
    status: 'pending',
    type: 'preview',
    error: null,
    title: null,
    item_count: 0,
    created_at: '2026-08-01T00:00:00+00:00',
    product_url: null,
    folder_label: 'Queued',
    last_stage: 'queued',
  },
]

function rowFor(id: string): HTMLTableRowElement {
  return screen.getByRole('link', { name: t.jobsOpenAria(id) }).closest('tr') as HTMLTableRowElement
}

function statusInRow(row: HTMLTableRowElement, status: JobSummary['status']): HTMLElement {
  return within(row).getByText(jobStatusLabel(status))
}

describe('JobList', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    FakeEventSource.install()
    clearTrackedRuns()
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 0, waiting: 0 })
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: JOBS })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(requestGooglePhotosAccessToken).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
    clearTrackedRuns()
    vi.unstubAllGlobals()
    FakeEventSource.install()
    vi.restoreAllMocks()
  })

  it('lists jobs in a table with number, id, operation, status, and start', async () => {
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: t.jobsHeading })).toBeInTheDocument()
    expect(screen.getByText(t.jobsLede)).toBeInTheDocument()
    expect(screen.getByText(t.jobsQueueSummary(0, 1, 0, 2))).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColNumber })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColId })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'אלבום' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Album' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Album link' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'קישור לאלבום' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColType })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColStatus })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColStart })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColEnd })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColDuration })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: t.jobsColError })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: t.photosHeading })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Photos URL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Google Photos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openPhotosAlbum })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openAlbum })).not.toBeInTheDocument()
    expect(screen.getAllByText(jobStatusLabel('done')).length).toBeGreaterThan(0)
    expect(screen.getByText(jobStatusLabel('failed'))).toBeInTheDocument()
    expect(screen.getByText(jobStatusLabel('pending'))).toBeInTheDocument()
    expect(screen.getByText(jobTypeLabel('upload'))).toBeInTheDocument()
    expect(screen.getAllByText(jobTypeLabel('preview')).length).toBeGreaterThan(0)
    expect(screen.queryByText('done')).not.toBeInTheDocument()
    expect(screen.queryByText('preview_ready')).not.toBeInTheDocument()
    expect(screen.queryByText('failed')).not.toBeInTheDocument()
    expect(screen.queryByText('pending')).not.toBeInTheDocument()
    expect(screen.queryByText('queued')).not.toBeInTheDocument()
    expect(screen.queryByText('error')).not.toBeInTheDocument()
    expect(screen.getByText('parse failed')).toBeInTheDocument()
    expect(screen.getByText('0:45')).toBeInTheDocument()
    expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    expect(screen.queryByText('חורף 2019')).not.toBeInTheDocument()

    expect(within(rowFor('job-summer')).getByText('42')).toBeInTheDocument()
    expect(within(rowFor('job-winter')).getByText('77')).toBeInTheDocument()
    expect(within(rowFor('job-broken')).getByText('3')).toBeInTheDocument()
    expect(within(rowFor('job-queued')).getByText('20')).toBeInTheDocument()

    const summerStatus = statusInRow(rowFor('job-summer'), 'done')
    expect(summerStatus).toHaveClass('job-list__status', 'job-list__status--done')
    expect(summerStatus).not.toHaveAttribute('aria-busy')

    const failedStatus = statusInRow(rowFor('job-broken'), 'failed')
    expect(failedStatus).toHaveClass('job-list__status', 'job-list__status--failed')
    expect(failedStatus).not.toHaveAttribute('aria-busy')

    const pendingStatus = statusInRow(rowFor('job-queued'), 'pending')
    expect(pendingStatus).toHaveClass('job-list__status', 'job-list__status--pending')
    expect(pendingStatus).not.toHaveAttribute('aria-busy')

    const openSummer = screen.getByRole('link', { name: t.jobsOpenAria('job-summer') })
    expect(openSummer).toHaveAttribute('href', '/jobs/job-summer')
    expect(screen.getByText('job-summer')).toBeInTheDocument()
  })

  it('shows unsupported Arles copy in the Error column for a failed scrape', async () => {
    const url = 'https://albums.example/album/index2012.html'
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = String(input)
      if (requestUrl.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (requestUrl.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({
          jobs: [
            {
              id: 'job-unsupported',
              number: 9,
              status: 'failed',
              type: 'scrape',
              error: `Not a supported Arles album: ${url}`,
              error_code: 'not_arles',
              title: null,
              item_count: 0,
              created_at: '2026-08-08T00:00:00+00:00',
              finished_at: '2026-08-08T00:00:02+00:00',
              product_url: null,
              scrape_url: url,
              last_stage: 'error',
            },
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    const row = await screen.findByRole('link', { name: t.jobsOpenAria('job-unsupported') })
    const tr = row.closest('tr') as HTMLTableRowElement
    expect(within(tr).getByText(jobStatusLabel('failed'))).toBeInTheDocument()
    expect(within(tr).getByText(t.errorScrapeUnsupported(url))).toBeInTheDocument()
    expect(within(tr).queryByText('Check the URL and headers')).not.toBeInTheDocument()
  })

  it('shows End time for terminal jobs and a dash while pending or running', async () => {
    const running: JobSummary = {
      id: 'job-busy',
      status: 'running',
      type: 'preview',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      updated_at: '2026-08-08T10:05:00+00:00',
      product_url: null,
      folder_label: 'Uploading',
      last_stage: 'ingest',
    }
    const cancelled: JobSummary = {
      id: 'job-stopped',
      status: 'cancelled',
      type: 'preview',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T09:00:00+00:00',
      finished_at: '2026-08-08T11:00:00+00:00',
      product_url: null,
      folder_label: 'Stopped',
      last_stage: 'cancelled',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({ jobs: [...JOBS, running, cancelled] })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-summer')
    expect(screen.getByRole('columnheader', { name: t.jobsColEnd })).toBeInTheDocument()

    const headers = screen.getAllByRole('columnheader').map((header) => header.textContent)
    expect(headers.indexOf(t.jobsColStart)).toBeLessThan(headers.indexOf(t.jobsColEnd))
    expect(headers.indexOf(t.jobsColEnd)).toBeLessThan(headers.indexOf(t.jobsColDuration))

    expect(rowFor('job-summer').querySelector('.job-list__end')).toHaveTextContent(
      formatJobDate('2012-08-02T10:00:45+00:00'),
    )
    expect(rowFor('job-winter').querySelector('.job-list__end')).toHaveTextContent(
      formatJobDate('2019-01-15T00:00:12+00:00'),
    )
    expect(rowFor('job-broken').querySelector('.job-list__end')).toHaveTextContent(
      formatJobDate('2020-01-01T00:00:05+00:00'),
    )
    expect(rowFor('job-stopped').querySelector('.job-list__end')).toHaveTextContent(
      formatJobDate('2026-08-08T11:00:00+00:00'),
    )

    const queuedEnd = rowFor('job-queued').querySelector('.job-list__end')
    expect(queuedEnd).toHaveTextContent(t.missingValue)

    const busyEnd = rowFor('job-busy').querySelector('.job-list__end')
    expect(busyEnd).toHaveTextContent(t.missingValue)
    expect(busyEnd).not.toHaveTextContent(formatJobDate('2026-08-08T10:05:00+00:00'))
  })

  it('links each id to job detail and has no album desk column', async () => {
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-summer')
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-summer') })).toHaveAttribute(
      'href',
      '/jobs/job-summer',
    )
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-winter') })).toHaveAttribute(
      'href',
      '/jobs/job-winter',
    )
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-broken') })).toHaveAttribute(
      'href',
      '/jobs/job-broken',
    )
    expect(screen.queryByRole('link', { name: t.openAlbum })).toBeNull()
    expect(
      screen.getAllByRole('link').some((link) => (link.getAttribute('href') ?? '').startsWith('/albums/')),
    ).toBe(false)
  })

  it('shows a pulsing running status without last_stage', async () => {
    const ingesting: JobSummary = {
      id: 'job-busy',
      status: 'running',
      type: 'preview',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      folder_label: 'Uploading',
      last_stage: 'ingest',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({ jobs: [...JOBS, ingesting] })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const busyRow = (await screen.findByRole('link', { name: t.jobsOpenAria('job-busy') })).closest(
      'tr',
    ) as HTMLTableRowElement
    const status = statusInRow(busyRow, 'running')
    expect(status).toHaveClass('job-list__status', 'job-list__status--running')
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(status.querySelector('.job-list__pulse')).toBeNull()
    expect(within(busyRow).queryByText('ingest')).not.toBeInTheDocument()
    expect(within(busyRow).queryByText('running')).not.toBeInTheDocument()
  })

  it('does not show last_stage in the status column', async () => {
    const spaced: JobSummary = {
      id: 'job-spaced',
      status: 'done',
      type: 'preview',
      error: null,
      title: 'Spaced album',
      item_count: 1,
      created_at: '2019-01-15T00:00:00+00:00',
      product_url: null,
      folder_label: 'SpacedFolder',
      duration_seconds: 1,
      last_stage: 'preview_ready',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      return jsonResponse({ jobs: [spaced] })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const row = (await screen.findByRole('link', { name: t.jobsOpenAria('job-spaced') })).closest(
      'tr',
    ) as HTMLTableRowElement
    const status = statusInRow(row, 'done')
    expect(status).toHaveClass('job-list__status--done')
    expect(within(row).queryByText('preview_ready')).not.toBeInTheDocument()
    expect(within(row).queryByText('Done')).not.toBeInTheDocument()
    expect(within(row).queryByText('done')).not.toBeInTheDocument()
  })

  it('refetches while a visible job is processing and stops when terminal', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const ingesting: JobSummary = {
      id: 'job-busy',
      status: 'running',
      type: 'preview',
      error: null,
      title: null,
      item_count: 0,
      created_at: new Date().toISOString(),
      product_url: null,
      folder_label: 'Uploading',
      last_stage: 'ingest',
    }
    const ready: JobSummary = {
      ...ingesting,
      status: 'done',
      type: 'preview',
      title: 'Ready album',
      item_count: 2,
      duration_seconds: 8,
      last_stage: 'preview_ready',
    }
    let listed = [ingesting]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({
          max_concurrent_jobs: 2,
          pending: listed[0]?.status === 'running' ? 0 : 0,
          running: listed[0]?.status === 'running' ? 1 : 0,
          waiting: 0,
        })
      }
      const payload = jsonResponse({ jobs: listed })
      if (listed[0]?.status === 'running') {
        listed = [ready]
      }
      return payload
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByText(jobStatusLabel('running'))).toBeInTheDocument()
    const callsAfterLoad = fetchMock.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_LIST_POLL_MS)
    })

    expect(fetchMock.mock.calls.length).toBeGreaterThan(callsAfterLoad)
    expect(await screen.findByText(jobStatusLabel('done'))).toBeInTheDocument()
    expect(screen.queryByText(jobStatusLabel('running'))).not.toBeInTheDocument()
    expect(screen.queryByText('ingest')).not.toBeInTheDocument()
    expect(screen.queryByText('preview_ready')).not.toBeInTheDocument()
    expect(statusInRow(rowFor('job-busy'), 'done')).toHaveClass('job-list__status--done')

    const callsAfterDone = fetchMock.mock.calls.length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(fetchMock.mock.calls.length).toBe(callsAfterDone)
  })

  it('shows the scrape type label and links id to job detail', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({
        jobs: [
          {
            id: 'job-scrape',
            status: 'running',
            type: 'scrape',
            error: null,
            title: 'albums.example',
            item_count: 0,
            created_at: '2026-08-08T00:00:00+00:00',
            product_url: null,
            folder_label: 'albums.example',
            preview_job_id: 'preview-early',
          } satisfies JobSummary,
        ],
      })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const row = (await screen.findByRole('link', { name: t.jobsOpenAria('job-scrape') })).closest(
      'tr',
    ) as HTMLTableRowElement
    expect(within(row).getByText(jobTypeLabel('scrape'))).toBeInTheDocument()
    expect(within(row).getByText(jobStatusLabel('running'))).toBeInTheDocument()
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-scrape') })).toHaveAttribute(
      'href',
      '/jobs/job-scrape',
    )
  })

  it('links a done scrape job to job detail, not an album desk', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      return jsonResponse({
        jobs: [
          {
            id: 'job-scrape',
            status: 'done',
            type: 'scrape',
            error: null,
            title: 'albums.example',
            item_count: 0,
            created_at: '2026-08-08T00:00:00+00:00',
            product_url: null,
            folder_label: null,
            preview_job_id: 'preview-from-scrape',
          } satisfies JobSummary,
        ],
      })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const row = (await screen.findByRole('link', { name: t.jobsOpenAria('job-scrape') })).closest(
      'tr',
    ) as HTMLTableRowElement
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()
    expect(within(row).queryByRole('link', { name: t.openAlbum })).toBeNull()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-scrape') })).toHaveAttribute(
      'href',
      '/jobs/job-scrape',
    )
    expect(
      screen.getAllByRole('link').some((link) => (link.getAttribute('href') ?? '').startsWith('/albums/')),
    ).toBe(false)
  })

  it('shows cancel on pending and running rows and posts cancel', async () => {
    const running: JobSummary = {
      id: 'job-busy',
      status: 'running',
      type: 'upload',
      error: null,
      title: 'Busy album',
      item_count: 2,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 1, waiting: 0 })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        return jsonResponse({ ...running, status: 'cancelled', error: null, preview: null, product_url: null })
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({
          jobs: [
            running,
            JOBS[0],
            JOBS[3],
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText(jobStatusLabel('running'))
    const busyRow = rowFor('job-busy')
    const queuedRow = rowFor('job-queued')
    expect(within(busyRow).getByRole('button', { name: t.cancelJob })).toBeInTheDocument()
    expect(within(queuedRow).getByRole('button', { name: t.cancelJob })).toBeInTheDocument()
    expect(within(rowFor('job-summer')).queryByRole('button', { name: t.cancelJob })).toBeNull()

    fireEvent.click(within(busyRow).getByRole('button', { name: t.cancelJob }))
    fireEvent.click(screen.getByRole('button', { name: t.confirmCancelJobYes }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            String(call[0]).endsWith('/api/jobs/job-busy/cancel') &&
            (call[1] as RequestInit)?.method === 'POST',
        ),
      ).toBe(true)
    })
  })

  it('loads cancel-preview children after Cancel and lists them as links', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day1',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 1, waiting: 0 })
      }
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [child] })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        return jsonResponse({
          ...hub,
          status: 'cancelled',
          error: null,
          preview: null,
          product_url: null,
        })
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: [hub, JOBS[0]] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const hubRow = (await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).closest(
      'tr',
    ) as HTMLTableRowElement
    fireEvent.click(within(hubRow).getByRole('button', { name: t.cancelJob }))

    expect(await screen.findByText(t.confirmCancelJobWithChildrenBody)).toBeInTheDocument()
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedCancelJobLabel(child)),
      }),
    ).toHaveAttribute('href', '/jobs/job-hub-day1')
    expect(screen.queryByText(t.confirmCancelJobBody)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: t.confirmCancelJobYes }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            String(call[0]).endsWith('/api/jobs/job-hub/cancel') &&
            (call[1] as RequestInit)?.method === 'POST',
        ),
      ).toBe(true)
    })
    const cancelPosts = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).endsWith('/api/jobs/job-hub/cancel') && (call[1] as RequestInit)?.method === 'POST',
    )
    expect(cancelPosts).toHaveLength(1)
  })

  it('keeps the simple cancel copy on the list when cancel-preview has no children', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 0, waiting: 0 })
      }
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.includes('/api/jobs')) {
        return jsonResponse({ jobs: JOBS })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByRole('link', { name: t.jobsOpenAria('job-queued') })
    fireEvent.click(within(rowFor('job-queued')).getByRole('button', { name: t.cancelJob }))
    expect(await screen.findByText(t.confirmCancelJobBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmCancelJobWithChildrenBody)).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('filters jobs by title, folder, id, and status', async () => {
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-summer')
    const search = screen.getByLabelText(t.jobsSearchLabel)

    fireEvent.change(search, { target: { value: 'SkiTrip' } })
    expect(screen.queryByText('job-summer')).not.toBeInTheDocument()
    expect(screen.getByText('job-winter')).toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'job-broken' } })
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-broken') })).toBeInTheDocument()
    expect(screen.queryByText('job-winter')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'preview' } })
    expect(screen.getByText('job-winter')).toBeInTheDocument()
    expect(screen.getAllByText(jobTypeLabel('preview')).length).toBeGreaterThan(0)
    expect(screen.queryByText('preview_ready')).not.toBeInTheDocument()
    expect(screen.queryByText('job-summer')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'pending' } })
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-queued') })).toBeInTheDocument()
    expect(statusInRow(rowFor('job-queued'), 'pending')).toHaveClass('job-list__status--pending')
    expect(screen.queryByText('job-summer')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'upload' } })
    expect(screen.getByText('job-summer')).toBeInTheDocument()
    expect(screen.getByText(jobTypeLabel('upload'))).toBeInTheDocument()
    expect(screen.queryByText('job-winter')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: '42' } })
    expect(screen.getByText('job-summer')).toBeInTheDocument()
    expect(screen.queryByText('job-winter')).not.toBeInTheDocument()
  })

  it('shows restart only on cancelled rows and creates a new job', async () => {
    const cancelled: JobSummary = {
      id: 'job-stopped',
      number: 12,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T09:00:00+00:00',
      finished_at: '2026-08-08T11:00:00+00:00',
      product_url: null,
      folder_label: 'Stopped',
      last_stage: 'cancelled',
    }
    const created: Job = {
      id: 'job-new',
      number: 13,
      status: 'pending',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      created_at: '2026-08-08T12:00:00+00:00',
    }
    let listed: JobSummary[] = [cancelled, ...JOBS]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        listed = [
          {
            id: created.id,
            number: created.number,
            status: 'pending',
            type: 'scrape',
            error: null,
            title: null,
            item_count: 0,
            created_at: created.created_at ?? null,
            product_url: null,
          },
          ...listed,
        ]
        return jsonResponse(created, 201)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: listed })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-stopped')
    expect(within(rowFor('job-stopped')).getByRole('button', { name: t.restartJob })).toBeInTheDocument()
    expect(within(rowFor('job-summer')).queryByRole('button', { name: t.restartJob })).toBeNull()
    expect(within(rowFor('job-queued')).queryByRole('button', { name: t.restartJob })).toBeNull()

    fireEvent.click(within(rowFor('job-stopped')).getByRole('button', { name: t.restartJob }))
    expect(screen.getByRole('dialog')).toHaveTextContent(t.confirmRestartJobBody)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))

    await waitFor(() => {
      expect(screen.getByRole('link', { name: t.jobsOpenAria('job-new') })).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-stopped') })).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        (call) =>
          String(call[0]).endsWith('/api/jobs/job-stopped/restart') &&
          (call[1] as RequestInit)?.method === 'POST',
      ),
    ).toBe(true)
    const restartPost = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).endsWith('/api/jobs/job-stopped/restart') &&
        (call[1] as RequestInit)?.method === 'POST',
    )
    expect(JSON.parse(String((restartPost?.[1] as RequestInit)?.body))).toEqual({})
  })

  it('asks all vs remaining when restarting a cancelled hub with scrape children', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const remainingChild = {
      id: 'job-hub-day2',
      number: 6,
      status: 'failed' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day2',
    }
    const doneChild = {
      id: 'job-hub-day1',
      number: 5,
      status: 'done' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day1',
    }
    const created: Job = {
      id: 'job-hub-new',
      number: 7,
      status: 'pending',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      created_at: '2026-08-08T12:00:00+00:00',
    }
    let listed: JobSummary[] = [hub, ...JOBS]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/restart-preview')) {
        return jsonResponse({
          descendants: [doneChild, remainingChild],
          done: [doneChild],
          remaining: [remainingChild],
        })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        listed = [
          {
            id: created.id,
            number: created.number,
            status: 'pending',
            type: 'scrape',
            error: null,
            title: null,
            item_count: 0,
            created_at: created.created_at ?? null,
            product_url: null,
          },
          ...listed,
        ]
        return jsonResponse(created, 201)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: listed })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-hub')
    fireEvent.click(within(rowFor('job-hub')).getByRole('button', { name: t.restartJob }))
    expect(await screen.findByText(t.confirmRestartJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmRestartJobBody)).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedRestartJobLabel(remainingChild)),
      }),
    ).toHaveAttribute('href', '/jobs/job-hub-day2')
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedRestartJobLabel(doneChild)),
      }),
    ).toHaveAttribute('href', '/jobs/job-hub-day1')

    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobRemaining }))
    await waitFor(() => {
      expect(screen.getByRole('link', { name: t.jobsOpenAria('job-hub-new') })).toBeInTheDocument()
    })
    const restartPost = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).endsWith('/api/jobs/job-hub/restart') &&
        (call[1] as RequestInit)?.method === 'POST',
    )
    expect(JSON.parse(String((restartPost?.[1] as RequestInit)?.body))).toEqual({ mode: 'remaining' })
  })

  it('posts restart all from the hub two-option dialog', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const remainingChild = {
      id: 'job-hub-day2',
      number: 6,
      status: 'failed' as const,
      type: 'scrape' as const,
      scrape_url: 'https://albums.example/day2',
    }
    const created: Job = {
      id: 'job-hub-new',
      number: 7,
      status: 'pending',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      created_at: '2026-08-08T12:00:00+00:00',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/restart-preview')) {
        return jsonResponse({
          descendants: [remainingChild],
          done: [],
          remaining: [remainingChild],
        })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        return jsonResponse(created, 201)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: [hub, ...JOBS] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-hub')
    fireEvent.click(within(rowFor('job-hub')).getByRole('button', { name: t.restartJob }))
    expect(await screen.findByText(t.confirmRestartJobWithChildrenBody)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobAll }))
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (call) =>
            String(call[0]).endsWith('/api/jobs/job-hub/restart') &&
            (call[1] as RequestInit)?.method === 'POST',
        ),
      ).toBe(true)
    })
    const restartPost = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).endsWith('/api/jobs/job-hub/restart') &&
        (call[1] as RequestInit)?.method === 'POST',
    )
    expect(JSON.parse(String((restartPost?.[1] as RequestInit)?.body))).toEqual({})
  })

  it('shows Waiting with Cancel and without Restart', async () => {
    const waiting: JobSummary = {
      id: 'job-waiting',
      number: 9,
      status: 'waiting',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      warnings: ['Child #12 failed: site down'],
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 1 })
      }
      return jsonResponse({ jobs: [waiting, ...JOBS] })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.jobsQueueSummary(0, 0, 1, 2))).toBeInTheDocument()
    const row = rowFor('job-waiting')
    expect(statusInRow(row, 'waiting')).toHaveClass('job-list__status--waiting')
    expect(within(row).getByRole('button', { name: t.cancelJob })).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: t.restartJob })).toBeNull()
    expect(within(row).getByText('Child #12 failed: site down')).toBeInTheDocument()
  })

  it('shows empty copy when there are no jobs', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      return jsonResponse({ jobs: [] })
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    expect(await screen.findByText(t.jobsEmpty)).toBeInTheDocument()
  })

  it('shows a spinner instead of empty until jobs arrive', async () => {
    let resolveJobs: ((value: Response) => void) | undefined
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.includes('/api/jobs')) {
        return await new Promise<Response>((resolve) => {
          resolveJobs = resolve
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText(t.loadingJobs)).toBeInTheDocument()
    expect(screen.queryByText(t.jobsEmpty)).not.toBeInTheDocument()

    resolveJobs?.(jsonResponse({ jobs: JOBS }))

    expect(await screen.findByText('job-summer')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows no-match copy when search filters everything out', async () => {
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    await screen.findByText('job-summer')
    fireEvent.change(screen.getByLabelText(t.jobsSearchLabel), { target: { value: 'zzzz' } })
    expect(screen.getByText(t.jobsNoMatches)).toBeInTheDocument()
  })

  it('shows newly spawned hub children on the next poll without remounting', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const childA: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    const childB: JobSummary = {
      id: 'job-hub-day2',
      number: 6,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:02+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day2',
    }
    let listed: JobSummary[] = [hub]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({
          max_concurrent_jobs: 2,
          pending: listed.filter((job) => job.status === 'pending').length,
          running: listed.filter((job) => job.status === 'running').length,
          waiting: listed.filter((job) => job.status === 'waiting').length,
        })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).not.toBeInTheDocument()

    listed = [{ ...hub, status: 'waiting' }, childA, childB]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_LIST_SCRAPE_POLL_MS)
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-hub-day2') })).toBeInTheDocument()
  })

  it('keeps polling for a tracked scrape even when the visible list is terminal', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [JOBS[0]]
    trackRun({ id: hub.id, kind: 'scrape', status: 'running', number: hub.number })
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-summer')
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub') })).not.toBeInTheDocument()

    listed = [hub, child, JOBS[0]]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOB_LIST_SCRAPE_POLL_MS)
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
  })

  it('refetches immediately when a tracked hub scrape emits a child event', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [hub]
    trackRun({ id: hub.id, kind: 'scrape', status: 'running', number: hub.number })
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).not.toBeInTheDocument()
    expect(FakeEventSource.find('job-hub')).toBeTruthy()

    listed = [{ ...hub, status: 'waiting' }, child]
    act(() => {
      FakeEventSource.find('job-hub')!.emit({
        job_id: hub.id,
        stage: 'child',
        message: child.id,
        current: 0,
        total: 0,
        extra: { child_id: child.id, type: 'scrape' },
        occurred_at: '2026-08-08T10:01:00+00:00',
      })
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
  })

  it('refetches immediately when a listed hub scrape emits a child event without trackRun', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [hub]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).not.toBeInTheDocument()
    await waitFor(() => {
      expect(FakeEventSource.find('job-hub')?.url).toBe('/api/jobs/job-hub/events?phase=scrape')
    })

    listed = [{ ...hub, status: 'waiting' }, child]
    act(() => {
      FakeEventSource.find('job-hub')!.emit({
        job_id: hub.id,
        stage: 'child',
        message: child.id,
        current: 0,
        total: 0,
        extra: { child_id: child.id, type: 'scrape' },
        occurred_at: '2026-08-08T10:01:00+00:00',
      })
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
  })

  it('polls a waiting hub scrape even when trackedRuns is empty', async () => {
    // Do not fake setInterval here: Testing Library waitFor polls with setInterval,
    // so a fake clock freezes retries and flakes on slow CI before SSE opens.
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'waiting',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    const preview: JobSummary = {
      id: 'job-hub-day1-preview',
      number: 6,
      status: 'pending',
      type: 'preview',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:02+00:00',
      product_url: null,
    }
    let listed: JobSummary[] = [hub]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({
          max_concurrent_jobs: 2,
          pending: listed.filter((job) => job.status === 'pending').length,
          running: listed.filter((job) => job.status === 'running').length,
          waiting: listed.filter((job) => job.status === 'waiting').length,
        })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).not.toBeInTheDocument()
    await waitFor(() => {
      expect(FakeEventSource.find('job-hub')?.url).toBe('/api/jobs/job-hub/events?phase=scrape')
    })

    listed = [hub, child, preview]
    await waitFor(
      () => {
        expect(
          screen.getByRole('link', { name: t.jobsOpenAria('job-hub-day1') }),
        ).toBeInTheDocument()
      },
      { timeout: JOB_LIST_SCRAPE_POLL_MS * 4 },
    )
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-hub-day1-preview') })).toBeInTheDocument()
  })

  it('refetches the list when the window is focused', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [hub]
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      return jsonResponse({ jobs: listed })
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).toBeInTheDocument()
    listed = [{ ...hub, status: 'waiting' }, child]
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })

    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
  })

  it('refetches after a cancel 409 so newly spawned children appear', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'running',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'pending',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [hub]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 1, waiting: 0 })
      }
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        listed = [{ ...hub, status: 'waiting' }, child]
        return jsonResponse({ detail: 'job already finished' }, 409)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: listed })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    const hubRow = (await screen.findByRole('link', { name: t.jobsOpenAria('job-hub') })).closest(
      'tr',
    ) as HTMLTableRowElement
    fireEvent.click(within(hubRow).getByRole('button', { name: t.cancelJob }))
    fireEvent.click(await screen.findByRole('button', { name: t.confirmCancelJobYes }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorCancel('HTTP 409: job already finished'),
    )
    expect(await screen.findByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).toBeInTheDocument()
  })

  it('shows a cancel error when cancel fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 0, waiting: 0 })
      }
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.endsWith('/cancel') && init?.method === 'POST') {
        return jsonResponse({ detail: 'too late' }, 409)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: JOBS })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    await screen.findByText('job-queued')
    fireEvent.click(within(rowFor('job-queued')).getByRole('button', { name: t.cancelJob }))
    fireEvent.click(await screen.findByRole('button', { name: t.confirmCancelJobYes }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorCancel('HTTP 409: too late'),
    )
  })

  it('shows a load error when the jobs list cannot be fetched', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      return jsonResponse({ detail: 'down' }, 503)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorJob('HTTP 503: down'),
    )
  })

  it('shows a restart error when restart fails', async () => {
    const cancelled: JobSummary = {
      id: 'job-stopped',
      number: 12,
      status: 'cancelled',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T09:00:00+00:00',
      finished_at: '2026-08-08T11:00:00+00:00',
      product_url: null,
      folder_label: 'Stopped',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        return jsonResponse({ detail: 'busy' }, 409)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: [cancelled] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    await screen.findByText('job-stopped')
    fireEvent.click(within(rowFor('job-stopped')).getByRole('button', { name: t.restartJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorRestart('HTTP 409: busy'),
    )
  })

  it('does not restart an upload when Google sign-in is cancelled', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new GoogleAuthCancelledError())
    const cancelled: JobSummary = {
      id: 'job-upload-stopped',
      number: 8,
      status: 'cancelled',
      type: 'upload',
      error: null,
      title: 'קיץ 2012',
      item_count: 3,
      created_at: '2012-08-02T10:00:00+00:00',
      finished_at: '2012-08-02T10:01:00+00:00',
      product_url: null,
      folder_label: 'Day1',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/restart') && init?.method === 'POST') {
        throw new Error('restart should not run after GIS cancel')
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: [cancelled] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    await screen.findByText('job-upload-stopped')
    fireEvent.click(within(rowFor('job-upload-stopped')).getByRole('button', { name: t.restartJob }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: t.confirmRestartJobYes }))
    await waitFor(() => {
      expect(requestGooglePhotosAccessToken).toHaveBeenCalled()
    })
    expect(screen.getByText('job-upload-stopped')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows hide on finished rows and archives after confirm', async () => {
    let listed: JobSummary[] = [...JOBS]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 1, running: 0, waiting: 0 })
      }
      if (url.endsWith('/archive') && init?.method === 'POST') {
        listed = listed.filter((job) => job.id !== 'job-summer')
        return jsonResponse({
          job: { ...JOBS[0], archived_at: '2026-08-08T12:00:00+00:00' },
          archived_ids: ['job-summer'],
        })
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: listed })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-summer')
    expect(within(rowFor('job-summer')).getByRole('button', { name: t.archiveJob })).toBeInTheDocument()
    expect(within(rowFor('job-broken')).getByRole('button', { name: t.archiveJob })).toBeInTheDocument()
    expect(within(rowFor('job-queued')).queryByRole('button', { name: t.archiveJob })).toBeNull()

    fireEvent.click(within(rowFor('job-summer')).getByRole('button', { name: t.archiveJob }))
    const dialog = new ConfirmDialogInteractor(t.confirmArchiveJobTitle)
    expect(dialog.find()).toHaveTextContent(t.confirmArchiveJobBody)
    dialog.confirm(t.confirmArchiveJobYes)

    await waitFor(() => {
      expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-summer') })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-winter') })).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some(
        (call) =>
          String(call[0]).endsWith('/api/jobs/job-summer/archive') &&
          (call[1] as RequestInit)?.method === 'POST',
      ),
    ).toBe(true)
  })

  it('removes cascaded child rows after archiving a hub', async () => {
    const hub: JobSummary = {
      id: 'job-hub',
      number: 4,
      status: 'done',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:00+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/hub/',
    }
    const child: JobSummary = {
      id: 'job-hub-day1',
      number: 5,
      status: 'done',
      type: 'scrape',
      error: null,
      title: null,
      item_count: 0,
      created_at: '2026-08-08T10:00:01+00:00',
      product_url: null,
      scrape_url: 'https://albums.example/day1',
    }
    let listed: JobSummary[] = [hub, child, JOBS[0]]
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/archive') && init?.method === 'POST') {
        listed = listed.filter((job) => job.id !== hub.id && job.id !== child.id)
        return jsonResponse({
          job: { ...hub, archived_at: '2026-08-08T12:00:00+00:00' },
          archived_ids: [hub.id, child.id],
        })
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: listed })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )

    await screen.findByText('job-hub')
    fireEvent.click(within(rowFor('job-hub')).getByRole('button', { name: t.archiveJob }))
    new ConfirmDialogInteractor(t.confirmArchiveJobTitle).confirm(t.confirmArchiveJobYes)

    await waitFor(() => {
      expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub') })).not.toBeInTheDocument()
    })
    expect(screen.queryByRole('link', { name: t.jobsOpenAria('job-hub-day1') })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-summer') })).toBeInTheDocument()
  })

  it('shows an archive error when hide fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/settings')) {
        return jsonResponse({ max_concurrent_jobs: 2, pending: 0, running: 0, waiting: 0 })
      }
      if (url.endsWith('/archive') && init?.method === 'POST') {
        return jsonResponse({ detail: 'job is still active' }, 409)
      }
      if (url.includes('/api/jobs') && (!init || init.method === 'GET')) {
        return jsonResponse({ jobs: JOBS })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    render(
      <MemoryRouter>
        <JobList />
      </MemoryRouter>,
    )
    await screen.findByText('job-summer')
    fireEvent.click(within(rowFor('job-summer')).getByRole('button', { name: t.archiveJob }))
    new ConfirmDialogInteractor(t.confirmArchiveJobTitle).confirm(t.confirmArchiveJobYes)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorArchive('HTTP 409: job is still active'),
    )
    expect(screen.getByRole('link', { name: t.jobsOpenAria('job-summer') })).toBeInTheDocument()
  })
})
