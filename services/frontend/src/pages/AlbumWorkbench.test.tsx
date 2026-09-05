import '@testing-library/jest-dom/vitest'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job, JobType } from '../api/types.ts'
import { affectedCancelJobLabel } from '../components/CancelJobDialog.tsx'
import { GoogleAuthCancelledError, requestGooglePhotosAccessToken } from '../lib/googleAuth.ts'
import { jobStatusLabel, t } from '../lib/language.ts'
import { getTrackedRuns, jobToastLabel } from '../lib/runTracker.ts'
import { getToasts } from '../lib/toast.ts'
import {
  CancelJobDialogInteractor,
  ConfirmDialogInteractor,
  FakeAlbumFiles,
  FakeEventSource,
  JobBuilder,
  PreviewItemBuilder,
  ReprocessConflictInteractor,
  ReprocessDialogInteractor,
  RoutedPageTestBase,
  jsonResponse,
  type FetchMockFn,
  type ScriptedFetchStrategy,
} from '../testing/index.ts'
import { AlbumWorkbench } from './AlbumWorkbench.tsx'

vi.mock('../lib/googleAuth.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/googleAuth.ts')>()
  return {
    ...actual,
    requestGooglePhotosAccessToken: vi.fn(),
  }
})

const PREVIEW_JOB = JobBuilder.preview().build()
const UPLOAD_JOB = JobBuilder.preview({
  id: 'job-upload-winter',
  type: 'upload',
  product_url: 'https://photos.example/winter',
  source_job_id: PREVIEW_JOB.id,
  preview: PREVIEW_JOB.preview,
}).build()

class WorkbenchHarness extends RoutedPageTestBase {
  protected override configureFetch(strategy: ScriptedFetchStrategy): void {
    strategy.on((request) => {
      if (request.path.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && request.method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (request.url.includes('/api/jobs?') || request.path.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      if (request.path.endsWith(`/api/jobs/${PREVIEW_JOB.id}/publish`) && request.method === 'POST') {
        return jsonResponse(UPLOAD_JOB, 201)
      }
      return null
    })
  }

  renderWorkbench(jobId = PREVIEW_JOB.id) {
    return this.renderInRouter(<AlbumWorkbench jobId={jobId} />, `/albums/${jobId}`)
  }

  renderHome(onJobCreated?: (id: string, type?: JobType) => void) {
    return this.renderInRouter(
      <AlbumWorkbench onJobCreated={onJobCreated} />,
      '/',
    )
  }
}

describe('AlbumWorkbench publish sign-in', () => {
  const harness = new WorkbenchHarness()
  let fetchMock: FetchMockFn

  beforeEach(() => {
    fetchMock = harness.install()
    vi.mocked(requestGooglePhotosAccessToken).mockReset()
  })

  afterEach(() => {
    harness.teardown()
  })

  it('shows the not-found page when the album job cannot be loaded', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'gone' }, 404))
    harness.renderWorkbench()
    expect(await screen.findByRole('heading', { name: t.notFoundHeading })).toBeInTheDocument()
    expect(screen.getByText(t.notFoundLede)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('surfaces a reprocess error after confirm', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        return jsonResponse({ detail: 'parse failed' }, 500)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    new ReprocessDialogInteractor().confirm(t.reprocess)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorReprocess('HTTP 500: parse failed'),
    )
  })

  it('keeps the preview desk when publish fails after sign-in', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.tok')
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/publish`) && method === 'POST') {
        return jsonResponse({ detail: 'quota' }, 500)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: t.publish }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorPublish('HTTP 500: quota'),
    )
    expect(screen.getByRole('button', { name: t.publish })).toBeEnabled()
  })

  it('shows a scrape error when web import fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse({ detail: 'unreachable' }, 502)
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorScrape('HTTP 502: unreachable'),
    )
  })

  it('shows unsupported Arles copy when the scrape job is already failed', async () => {
    const url = 'https://albums.example/album/index2012.html'
    const failed = JobBuilder.scrape({
      id: 'scrape-unsupported',
      status: 'failed',
      error: `Not a supported Arles album: ${url}`,
      error_code: 'not_arles',
      scrape_url: url,
      url,
    }).build()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (requestUrl.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse(failed, 201)
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: url },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(t.errorScrapeUnsupported(url))
    expect(alert).not.toHaveTextContent('Check the URL and headers')
    expect(screen.getByText(jobStatusLabel('failed'))).toBeInTheDocument()
  })

  it('shows a preview error when folder ingest fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if ((url.endsWith('/api/jobs') || url.includes('/api/jobs?')) && method === 'POST') {
        return jsonResponse({ detail: 'invalid album' }, 400)
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorPreview('HTTP 400: invalid album'),
    )
  })

  it('shows a friendly too-large message on HTTP 413 without folder layout advice', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if ((url.endsWith('/api/jobs') || url.includes('/api/jobs?')) && method === 'POST') {
        return new Response('<html><h1>Request Entity Too Large</h1></html>', {
          status: 413,
          headers: { 'Content-Type': 'text/html' },
        })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(t.errorPayloadTooLarge)
    expect(alert).not.toHaveTextContent(/index\.html/)
    expect(alert).not.toHaveTextContent(/<html/i)
  })

  it('marks a caption as dirty when edited on the workbench', async () => {
    harness.renderWorkbench()
    fireEvent.change(await screen.findByLabelText(t.descriptionLabel), {
      target: { value: 'כיתוב חדש' },
    })
    expect(screen.getByRole('button', { name: t.save })).toBeEnabled()
    expect(screen.getByText(t.modified)).toBeInTheDocument()
  })

  it('returns Publish to idle when Google sign-in is cancelled', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new GoogleAuthCancelledError())
    harness.renderWorkbench()

    const publish = await screen.findByRole('button', { name: t.publish })
    fireEvent.click(publish)

    expect(await screen.findByRole('alert')).toHaveTextContent(t.signInCancelled)
    expect(screen.getByRole('button', { name: t.publish })).toBeEnabled()
    expect(screen.queryByRole('button', { name: t.alreadyRunning })).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/publish'),
      expect.anything(),
    )
  })

  it('surfaces real Google API errors via explainFailure and unsticks Publish', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new Error('invalid_grant'))
    harness.renderWorkbench()

    fireEvent.click(await screen.findByRole('button', { name: t.publish }))

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errorPublish('invalid_grant'))
    expect(screen.getByRole('button', { name: t.publish })).toBeEnabled()
  })

  it('publishes after a successful Google sign-in', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.tok')
    harness.renderWorkbench()

    fireEvent.click(await screen.findByRole('button', { name: t.publish }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/jobs/${PREVIEW_JOB.id}/publish`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ access_token: 'ya29.tok' }),
        }),
      )
    })
    expect(await screen.findByRole('button', { name: t.reupload })).toBeEnabled()
    expect(screen.getByText(PREVIEW_JOB.id)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openPhotosAlbum })).toHaveAttribute(
      'href',
      UPLOAD_JOB.product_url,
    )
    expect(
      FakeEventSource.instances.some((source) => source.url.includes(UPLOAD_JOB.id)),
    ).toBe(true)
    expect(getToasts()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunSubmitted(jobToastLabel(UPLOAD_JOB.id, UPLOAD_JOB.number)),
          href: `/jobs/${UPLOAD_JOB.id}`,
          linkLabel: t.toastOpenRun,
        }),
      ]),
    )
    expect(getTrackedRuns().some((run) => run.id === UPLOAD_JOB.id && run.kind === 'upload')).toBe(
      true,
    )
  })

  it('re-authenticates and retries publish after Google returns 401', async () => {
    vi.mocked(requestGooglePhotosAccessToken)
      .mockResolvedValueOnce('ya29.old')
      .mockResolvedValueOnce('ya29.new')
    let publishCalls = 0
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/publish`) && method === 'POST') {
        publishCalls += 1
        const body = JSON.parse(String(init?.body)) as { access_token?: string }
        if (publishCalls === 1) {
          expect(body.access_token).toBe('ya29.old')
          return jsonResponse({ detail: 'invalid token' }, 401)
        }
        expect(body.access_token).toBe('ya29.new')
        return jsonResponse(UPLOAD_JOB, 201)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    fireEvent.click(await screen.findByRole('button', { name: t.publish }))

    await waitFor(() => {
      expect(requestGooglePhotosAccessToken).toHaveBeenCalledTimes(2)
    })
    expect(await screen.findByRole('button', { name: t.reupload })).toBeEnabled()
    expect(publishCalls).toBe(2)
  })

  it('does not submit-toast when Google sign-in is cancelled', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new GoogleAuthCancelledError())
    harness.renderWorkbench()

    fireEvent.click(await screen.findByRole('button', { name: t.publish }))
    expect(await screen.findByRole('alert')).toHaveTextContent(t.signInCancelled)
    expect(
      getToasts().some(
        (item) => item.message === t.toastRunSubmitted(jobToastLabel(UPLOAD_JOB.id, UPLOAD_JOB.number)),
      ),
    ).toBe(false)
    expect(getTrackedRuns()).toEqual([])
  })

  it('shows already-running when the stored job is uploading', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({ ...PREVIEW_JOB, status: 'running', type: 'upload' })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    expect(await screen.findByRole('button', { name: t.alreadyRunning })).toBeDisabled()
  })

  it('lists child jobs in the cancel modal when the preview has a pending upload', async () => {
    const runningPreview: Job = { ...PREVIEW_JOB, status: 'running' }
    const uploadChild = {
      id: 'job-upload-pending',
      number: 11,
      status: 'pending' as const,
      type: 'upload' as const,
      title: PREVIEW_JOB.preview!.title,
      parent_job_id: PREVIEW_JOB.id,
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [uploadChild] })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/cancel`) && method === 'POST') {
        return jsonResponse({ ...runningPreview, status: 'cancelled' })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(runningPreview)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    const cancel = new CancelJobDialogInteractor()

    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    expect(await screen.findByText(t.confirmCancelJobWithChildrenBody)).toBeInTheDocument()
    expect(
      screen.getByRole('link', {
        name: t.jobsOpenAria(affectedCancelJobLabel(uploadChild)),
      }),
    ).toHaveAttribute('href', `/jobs/${uploadChild.id}`)

    cancel.confirmCancelJob()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/jobs/${PREVIEW_JOB.id}/cancel`,
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('submit-toasts immediately when publish returns a running upload', async () => {
    const runningUpload: Job = {
      ...UPLOAD_JOB,
      status: 'running',
      product_url: null,
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/publish`) && method === 'POST') {
        return jsonResponse(runningUpload, 201)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.tok')
    harness.renderWorkbench()

    fireEvent.click(await screen.findByRole('button', { name: t.publish }))

    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunSubmitted(jobToastLabel(runningUpload.id, runningUpload.number)),
            href: `/jobs/${runningUpload.id}`,
            linkLabel: t.toastOpenRun,
          }),
        ]),
      )
    })
    expect(await screen.findByRole('button', { name: t.alreadyRunning })).toBeDisabled()
    expect(screen.queryByRole('link', { name: t.openPhotosAlbum })).not.toBeInTheDocument()
    expect(
      getTrackedRuns().some((run) => run.id === runningUpload.id && run.kind === 'upload'),
    ).toBe(true)
  })

  it('toasts reprocess as a new preview run', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        return jsonResponse({
          ...PREVIEW_JOB,
          preview: { ...PREVIEW_JOB.preview!, title: 'Reparsed' },
        })
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    const reprocess = new ReprocessDialogInteractor()

    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    reprocess.expectOpen()
    reprocess.confirm(t.reprocess)

    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunSubmitted(jobToastLabel(PREVIEW_JOB.id, PREVIEW_JOB.number)),
            href: `/jobs/${PREVIEW_JOB.id}`,
            linkLabel: t.toastOpenRun,
          }),
        ]),
      )
    })
    expect(
      getTrackedRuns().some((run) => run.id === PREVIEW_JOB.id && run.kind === 'preview'),
    ).toBe(true)
  })

  it('asks to re-download web albums and skips the request on cancel', async () => {
    const webJob: Job = {
      ...PREVIEW_JOB,
      id: 'job-web',
      import_origin: 'web',
      parent_job_id: 'scrape-parent',
      scrape_url: 'https://albums.example/day1',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${webJob.id}`) && method === 'GET') {
        return jsonResponse(webJob)
      }
      if (url.endsWith(`/api/jobs/${webJob.id}/reprocess`) && method === 'POST') {
        return jsonResponse(webJob)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench(webJob.id)
    const reprocess = new ReprocessDialogInteractor(true)

    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    await reprocess.wait()
    expect(screen.queryByRole('dialog', { name: t.confirmReprocess })).not.toBeInTheDocument()
    reprocess.cancel()

    reprocess.expectClosed()
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes('/reprocess')),
    ).toBe(false)
  })

  it('shows the conflict dialog for unsaved edits and skips POST on cancel', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    const conflict = new ReprocessConflictInteractor()

    fireEvent.change(await screen.findByLabelText(t.titleLabel), {
      target: { value: 'Edited title' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.reprocess }))

    const dialog = conflict.expectOpen()
    expect(dialog).toHaveTextContent(t.confirmReprocessConflictUnsaved)
    expect(screen.queryByRole('dialog', { name: t.confirmReprocess })).not.toBeInTheDocument()
    conflict.cancel()

    conflict.expectClosed()
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes('/reprocess')),
    ).toBe(false)
  })

  it('overwrites the same job from the conflict dialog', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse({ ...PREVIEW_JOB, user_edited: true })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        return jsonResponse({
          ...PREVIEW_JOB,
          user_edited: false,
          preview: { ...PREVIEW_JOB.preview!, title: 'Reparsed' },
        })
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    const conflict = new ReprocessConflictInteractor()

    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    const dialog = await conflict.wait()
    expect(dialog).toHaveTextContent(t.confirmReprocessConflictSaved)
    conflict.overwrite()

    await waitFor(() => {
      expect(screen.getByLabelText(t.titleLabel)).toHaveValue('Reparsed')
    })
    expect(
      fetchMock.mock.calls.some((call) => {
        const url = String(call[0])
        const init = call[1] as RequestInit | undefined
        if (!url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) || init?.method !== 'POST') {
          return false
        }
        return JSON.parse(String(init.body ?? '{}')).mode === 'overwrite'
      }),
    ).toBe(true)
  })

  it('creates a new album from the conflict dialog and navigates to it', async () => {
    const created: Job = {
      ...PREVIEW_JOB,
      id: 'job-reprocessed',
      user_edited: false,
      preview: { ...PREVIEW_JOB.preview!, title: 'Reprocessed · חורף 2019' },
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse({ ...PREVIEW_JOB, user_edited: true })
      }
      if (url.endsWith(`/api/jobs/${created.id}`) && method === 'GET') {
        return jsonResponse(created)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        return jsonResponse(created)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    const { router } = harness.renderWorkbench()
    const conflict = new ReprocessConflictInteractor()

    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    await conflict.wait()
    conflict.createNew()

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/albums/${created.id}`)
    })
    expect(
      fetchMock.mock.calls.some((call) => {
        const url = String(call[0])
        const init = call[1] as RequestInit | undefined
        if (!url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) || init?.method !== 'POST') {
          return false
        }
        const body = JSON.parse(String(init.body ?? '{}')) as { mode?: string; title_prefix?: string }
        return body.mode === 'new' && body.title_prefix === t.reprocessTitlePrefix
      }),
    ).toBe(true)
    expect(getToasts()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunSubmitted(jobToastLabel(created.id, created.number)),
          href: `/jobs/${created.id}`,
          linkLabel: t.toastOpenRun,
        }),
      ]),
    )
  })

  it('reprocesses a web album after the download confirm', async () => {
    const webJob: Job = {
      ...PREVIEW_JOB,
      id: 'job-web',
      import_origin: 'web',
      parent_job_id: 'scrape-parent',
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${webJob.id}`) && method === 'GET') {
        return jsonResponse(webJob)
      }
      if (url.endsWith(`/api/jobs/${webJob.id}/reprocess`) && method === 'POST') {
        return jsonResponse({
          ...webJob,
          preview: { ...webJob.preview!, title: 'Re-downloaded' },
        })
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench(webJob.id)
    const reprocess = new ReprocessDialogInteractor(true)

    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    await reprocess.wait()
    reprocess.confirm(t.reprocess)

    await waitFor(() => {
      expect(screen.getByLabelText(t.titleLabel)).toHaveValue('Re-downloaded')
    })
    expect(
      fetchMock.mock.calls.some((call) => {
        const url = String(call[0])
        const init = call[1] as RequestInit | undefined
        return url.endsWith(`/api/jobs/${webJob.id}/reprocess`) && init?.method === 'POST'
      }),
    ).toBe(true)
  })

  it('requests GIS then sends auto-publish token when the toggle is on', async () => {
    const scrapeJob: Job = JobBuilder.scrape({
      id: 'scrape-auto',
      auto_publish: true,
    }).build()
    const onJobCreated = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse(scrapeJob, 201)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.auto')
    harness.renderHome(onJobCreated)

    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    await waitFor(() => {
      expect(onJobCreated).toHaveBeenCalledWith('scrape-auto', 'scrape')
    })
    expect(requestGooglePhotosAccessToken).toHaveBeenCalledTimes(1)
    const scrapeCall = fetchMock.mock.calls.find((call) => String(call[0]) === '/api/jobs/scrape')
    expect(JSON.parse(String((scrapeCall![1] as RequestInit).body))).toEqual({
      url: 'https://gallery.example/index.html',
      auto_publish: true,
      access_token: 'ya29.auto',
    })
  })

  it('does not start a scrape job when Google sign-in is cancelled', async () => {
    const onJobCreated = vi.fn()
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new GoogleAuthCancelledError())
    harness.renderHome(onJobCreated)

    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(await screen.findByRole('alert')).toHaveTextContent(t.signInCancelled)
    expect(onJobCreated).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/jobs/scrape',
      expect.anything(),
    )
  })

  it('does not request GIS when auto-publish is off', async () => {
    const scrapeJob: Job = JobBuilder.scrape({ id: 'scrape-wb' }).build()
    const onJobCreated = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse(scrapeJob, 201)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderHome(onJobCreated)

    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    await waitFor(() => {
      expect(onJobCreated).toHaveBeenCalledWith('scrape-wb', 'scrape')
    })
    expect(requestGooglePhotosAccessToken).not.toHaveBeenCalled()
  })

  it('starts a scrape job from the web import form', async () => {
    const scrapeJob: Job = JobBuilder.scrape({ id: 'scrape-wb' }).build()
    const onJobCreated = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse(scrapeJob, 201)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderHome(onJobCreated)

    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    await waitFor(() => {
      expect(onJobCreated).toHaveBeenCalledWith('scrape-wb', 'scrape')
    })
    expect(getTrackedRuns().some((run) => run.id === 'scrape-wb' && run.kind === 'scrape')).toBe(
      true,
    )
    expect(getToasts()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunSubmitted(jobToastLabel(scrapeJob.id, scrapeJob.number)),
          href: '/jobs/scrape-wb',
        }),
      ]),
    )
  })

  it('shows re-upload when the album was already published', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          status: 'done',
          type: 'upload',
          product_url: 'https://photos.example/winter',
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    expect(await screen.findByRole('button', { name: t.reupload })).toBeEnabled()
  })

  it('shows the multi-index flag when the preview spans several index pages', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          preview: { ...PREVIEW_JOB.preview!, multi_index: true },
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    expect(await screen.findByText(t.multiIndex)).toBeInTheDocument()
  })

  it('surfaces a save error without leaving the editor', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'PATCH') {
        return jsonResponse({ detail: 'write failed' }, 500)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    fireEvent.change(await screen.findByLabelText(t.titleLabel), {
      target: { value: 'New title' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.save }))

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errorSave('HTTP 500: write failed'))
    expect(screen.getByRole('button', { name: t.save })).toBeEnabled()
  })

  it('marks journal heading and body as dirty when edited', async () => {
    const withJournal = {
      ...PREVIEW_JOB,
      preview: {
        ...PREVIEW_JOB.preview!,
        journal: { heading: 'יומן', paragraphs: ['פסקה'] },
      },
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse(withJournal)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    fireEvent.change(await screen.findByLabelText(t.journalHeadingLabel), {
      target: { value: 'כותרת חדשה' },
    })
    fireEvent.change(screen.getByLabelText(t.journalBodyLabel), {
      target: { value: 'פסקה אחרת' },
    })
    expect(screen.getByRole('button', { name: t.save })).toBeEnabled()
    expect(screen.getAllByText(t.modified).length).toBeGreaterThan(0)
  })

  it('shows a video placeholder when the workbench item has no still thumb', async () => {
    const videoItem = PreviewItemBuilder.video({ thumb_relpath: null }).build()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          preview: { ...PREVIEW_JOB.preview!, items: [videoItem] },
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    await screen.findByRole('button', { name: t.openVideoPreviewAria(videoItem.id) })
    expect(document.querySelector('.preview-card__video-placeholder')).toBeTruthy()
    expect(document.querySelector('img.preview-card__thumb')).toBeNull()
  })

  it('opens a video lightbox with play/thumb media URLs from the workbench', async () => {
    const videoItem = PreviewItemBuilder.video().build()
    const videoJob = JobBuilder.preview({
      preview: {
        ...PREVIEW_JOB.preview!,
        items: [videoItem],
      },
    }).build()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/api/jobs/${videoJob.id}`)) {
        return jsonResponse(videoJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    const open = await screen.findByRole('button', { name: t.openVideoPreviewAria(videoItem.id) })
    const card = open.closest('.preview-card')
    expect(card?.querySelector('img.preview-card__thumb')).toHaveAttribute(
      'src',
      `/api/jobs/${videoJob.id}/media/${videoItem.id}?variant=thumb`,
    )
    expect(card?.querySelector('.preview-card__video-badge')?.textContent).toBe(t.videoBadge)
    fireEvent.click(open)

    const video = document.querySelector('video')
    expect(video).toHaveAttribute('src', `/api/jobs/${videoJob.id}/media/${videoItem.id}?variant=play`)
    expect(video).toHaveAttribute('poster', `/api/jobs/${videoJob.id}/media/${videoItem.id}?variant=thumb`)
    expect(video).toHaveAttribute('aria-label', t.videoPreviewAria(videoItem.id))
  })

  it('uses thumb URLs in the grid and original in the image lightbox', async () => {
    const imageItem = PreviewItemBuilder.jpeg().build()
    const imageJob = JobBuilder.preview({
      preview: {
        ...PREVIEW_JOB.preview!,
        items: [imageItem],
      },
    }).build()
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/api/jobs/${imageJob.id}`)) {
        return jsonResponse(imageJob)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    const open = await screen.findByRole('button', {
      name: t.openPreviewAria(imageItem.id),
    })
    const card = open.closest('.preview-card')
    expect(card?.querySelector('img.preview-card__thumb')).toHaveAttribute(
      'src',
      `/api/jobs/${imageJob.id}/media/${imageItem.id}?variant=thumb`,
    )
    fireEvent.click(open)
    const lightboxImg = document.querySelector('.image-preview-modal img')
    expect(lightboxImg).toHaveAttribute(
      'src',
      `/api/jobs/${imageJob.id}/media/${imageItem.id}`,
    )
  })

  it('marks the gallery description dirty and saves edits', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'PATCH') {
        const body = JSON.parse(String(init?.body ?? '{}')) as { description?: string }
        return jsonResponse({
          ...PREVIEW_JOB,
          preview: { ...PREVIEW_JOB.preview!, description: body.description ?? 'חדש' },
        })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    fireEvent.change(await screen.findByLabelText(t.galleryDescriptionLabel), {
      target: { value: 'תיאור חדש' },
    })
    expect(screen.getByLabelText(t.galleryDescriptionLabel)).toHaveAccessibleDescription(t.modifiedAria)
    expect(screen.getByRole('button', { name: t.save })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: t.save }))
    expect(await screen.findByText(t.saved)).toBeInTheDocument()
    expect(getToasts()).toEqual(expect.arrayContaining([expect.objectContaining({ message: t.saved })]))
    expect(screen.getByLabelText(t.galleryDescriptionLabel)).toHaveValue('תיאור חדש')
  })

  it('shows Waiting and cancel on a waiting preview job', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({ ...PREVIEW_JOB, status: 'waiting' })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    expect(await screen.findByText(jobStatusLabel('waiting'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.cancelJob })).toBeInTheDocument()
  })

  it('shows a cancel error when cancel fails on the workbench', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith('/cancel-preview')) {
        return jsonResponse({ descendants: [] })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/cancel`) && method === 'POST') {
        return jsonResponse({ detail: 'too late' }, 409)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({ ...PREVIEW_JOB, status: 'running' })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: t.cancelJob }))
    new CancelJobDialogInteractor().confirmCancelJob()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorCancel('HTTP 409: too late'),
    )
  })

  it('shows preparing when the stored job has no preview yet', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({ ...PREVIEW_JOB, status: 'pending', preview: null })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    expect(await screen.findByText(t.preparing)).toBeInTheDocument()
    expect(screen.getByText(jobStatusLabel('pending'))).toBeInTheDocument()
  })

  it('shows a failed album without preview', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          status: 'failed',
          error: 'missing index.html',
          preview: null,
        })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    expect(await screen.findByRole('alert')).toHaveTextContent('missing index.html')
    expect(screen.getByText(jobStatusLabel('failed'))).toBeInTheDocument()
  })

  it('shows cancelled copy when the stored job was cancelled without preview', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          status: 'cancelled',
          error: null,
          preview: null,
        })
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    expect(await screen.findByRole('alert')).toHaveTextContent(t.toastRunCancelled)
  })

  it('polls until a pending album preview becomes ready', async () => {
    const intervals: Array<() => void> = []
    const intervalSpy = vi.spyOn(window, 'setInterval').mockImplementation((handler: TimerHandler) => {
      if (typeof handler === 'function') {
        intervals.push(handler as () => void)
      }
      return 1 as unknown as number
    })
    const clearSpy = vi.spyOn(window, 'clearInterval').mockImplementation(() => undefined)

    let current: Job = { ...PREVIEW_JOB, status: 'running', preview: null }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse(current)
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    expect(await screen.findByText(t.preparing)).toBeInTheDocument()

    current = PREVIEW_JOB
    await waitFor(() => expect(intervals.length).toBeGreaterThan(0))
    await act(async () => {
      intervals.forEach((tick) => tick())
    })
    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue(PREVIEW_JOB.preview!.title)
    expect(screen.getByText(t.previewReady)).toBeInTheDocument()
    intervalSpy.mockRestore()
    clearSpy.mockRestore()
  })

  it('picks up a related upload run from the jobs list', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({
          jobs: [
            {
              id: UPLOAD_JOB.id,
              status: 'done',
              type: 'upload',
              error: null,
              title: PREVIEW_JOB.preview!.title,
              item_count: 1,
              created_at: '2019-01-15T01:00:00+00:00',
              product_url: UPLOAD_JOB.product_url,
              source_job_id: PREVIEW_JOB.id,
            },
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()
    expect(await screen.findByRole('link', { name: t.openPhotosAlbum })).toHaveAttribute(
      'href',
      UPLOAD_JOB.product_url,
    )
    expect(screen.getByRole('button', { name: t.reupload })).toBeEnabled()
  })

  it('keeps the workbench in working phase while reprocess is pending', async () => {
    let current: Job = PREVIEW_JOB
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/reprocess`) && method === 'POST') {
        current = { ...PREVIEW_JOB, status: 'waiting' }
        return jsonResponse(current)
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(current)
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderWorkbench()
    const reprocess = new ReprocessDialogInteractor()
    fireEvent.click(await screen.findByRole('button', { name: t.reprocess }))
    reprocess.expectOpen()
    reprocess.confirm(t.reprocess)
    await waitFor(() => {
      expect(screen.getByText(jobStatusLabel('waiting'))).toBeInTheDocument()
    })
    expect(screen.getByText(t.reprocessing)).toBeInTheDocument()
  })

  it('applies publish SSE lifecycle updates for a running upload', async () => {
    const runningUpload: Job = { ...UPLOAD_JOB, status: 'running', product_url: null }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`) && method === 'GET') {
        return jsonResponse(PREVIEW_JOB)
      }
      if (url.endsWith(`/api/jobs/${UPLOAD_JOB.id}`) && method === 'GET') {
        return jsonResponse({ ...UPLOAD_JOB, status: 'done' })
      }
      if (url.includes('/api/jobs?') || url.endsWith('/api/jobs')) {
        return jsonResponse({ jobs: [] })
      }
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}/publish`) && method === 'POST') {
        return jsonResponse(runningUpload, 201)
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.tok')
    harness.renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: t.publish }))
    await waitFor(() => {
      expect(FakeEventSource.find(UPLOAD_JOB.id)).toBeTruthy()
    })
    FakeEventSource.find(UPLOAD_JOB.id)!.emit({
      job_id: UPLOAD_JOB.id,
      stage: 'done',
      message: 'finished',
      current: 1,
      total: 1,
      extra: null,
    })
    expect(await screen.findByText(t.publishedStatus)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openPhotosAlbum })).toHaveAttribute(
      'href',
      UPLOAD_JOB.product_url,
    )
  })

  it('registers beforeunload while the preview is dirty', async () => {
    harness.renderWorkbench()
    fireEvent.change(await screen.findByLabelText(t.titleLabel), { target: { value: 'חדש' } })
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('shows an upload progress bar while folder files are posting', async () => {
    let release!: (value: Response) => void
    const held = new Promise<Response>((resolve) => {
      release = resolve
    })
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if ((url.endsWith('/api/jobs') || url.includes('/api/jobs?')) && method === 'POST') {
        return held
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))

    expect(await screen.findByRole('progressbar')).toBeInTheDocument()
    expect(screen.getByText(t.sendingFiles(files.length))).toBeInTheDocument()

    await act(async () => {
      release(jsonResponse(PREVIEW_JOB, 201))
    })
    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    })
  })

  it('asks to overwrite when folder ingest hits an existing album', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if ((url.endsWith('/api/jobs') || url.includes('/api/jobs?')) && method === 'POST') {
        if (url.includes('overwrite=true')) {
          return jsonResponse(PREVIEW_JOB, 201)
        }
        return jsonResponse(
          { detail: { code: 'album_exists', existing_id: 'job-existing', title: 'קיץ 2012' } },
          409,
        )
      }
      return jsonResponse({ jobs: [] })
    })
    harness.renderHome()
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))

    const overwrite = new ConfirmDialogInteractor(t.confirmOverwriteAlbumTitle('קיץ 2012'))
    expect(await overwrite.wait()).toHaveTextContent(t.confirmOverwriteAlbumBody)
    expect(screen.getByRole('link', { name: t.openExistingAlbum })).toHaveAttribute(
      'href',
      '/albums/job-existing',
    )
    overwrite.confirm(t.confirmOverwriteAlbumYes)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('overwrite=true'))).toBe(
        true,
      )
    })
  })

  it('tracks upload children when folder import auto-publishes', async () => {
    const created = { ...PREVIEW_JOB, id: 'job-folder-auto', status: 'pending' as const, preview: null }
    const uploadChild = {
      id: 'job-folder-upload',
      number: 9,
      status: 'pending' as const,
      type: 'upload' as const,
      parent_job_id: created.id,
    }
    const onJobCreated = vi.fn()
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      if ((url.endsWith('/api/jobs') || url.includes('/api/jobs?')) && method === 'POST') {
        return jsonResponse(created, 201)
      }
      if (url.endsWith(`/api/jobs/${created.id}/children`) && method === 'GET') {
        return jsonResponse({ jobs: [uploadChild] })
      }
      return jsonResponse({ jobs: [] })
    })
    vi.mocked(requestGooglePhotosAccessToken).mockResolvedValueOnce('ya29.folder')
    harness.renderHome(onJobCreated)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))

    await waitFor(() => {
      expect(onJobCreated).toHaveBeenCalledWith(created.id, 'preview')
    })
    expect(getTrackedRuns().some((run) => run.id === uploadChild.id && run.kind === 'upload')).toBe(
      true,
    )
  })

  it('surfaces a Google error when folder auto-publish sign-in fails', async () => {
    vi.mocked(requestGooglePhotosAccessToken).mockRejectedValueOnce(new Error('invalid_grant'))
    harness.renderHome()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const files = FakeAlbumFiles.day1Index()
    FakeAlbumFiles.assignToInput(input, files)
    fireEvent.change(input, { target: { files } })
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    expect(await screen.findByRole('alert')).toHaveTextContent(t.errorPublish('invalid_grant'))
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).startsWith('/api/jobs') && (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(false)
  })
})

const MISMATCH_ITEM = PreviewItemBuilder.winter()
  .withDates('2019-01-15', '2024-08-01T12:00:00')
  .build()

const DATE_MISMATCH_COPY = `${t.dateMismatchBefore}${t.fieldTakenOn}${t.dateMismatchJoin}${t.fieldMtime}${t.dateMismatchAfter}`

describe('AlbumWorkbench date mismatch', () => {
  const harness = new WorkbenchHarness()
  let fetchMock: FetchMockFn

  beforeEach(() => {
    fetchMock = harness.install()
  })

  afterEach(() => {
    harness.teardown()
  })

  it('shows mismatch warning for folder-origin albums', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          import_origin: 'folder',
          preview: { ...PREVIEW_JOB.preview!, items: [MISMATCH_ITEM] },
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    await screen.findByText(MISMATCH_ITEM.id)
    expect(document.querySelector('.preview-card__note')?.textContent).toBe(DATE_MISMATCH_COPY)
    expect(document.querySelector('.preview-card__meta--differ')).toBeTruthy()
  })

  it('hides mismatch warning for web-origin albums even when days differ', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          import_origin: 'web',
          parent_job_id: 'scrape-parent',
          preview: { ...PREVIEW_JOB.preview!, items: [MISMATCH_ITEM] },
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    await screen.findByText(MISMATCH_ITEM.id)
    expect(document.querySelector('.preview-card__note')).toBeNull()
    expect(document.querySelector('.preview-card__meta--differ')).toBeNull()
    expect(screen.getByText('2019-01-15')).toBeInTheDocument()
    expect(screen.getByText('2024-08-01T12:00:00')).toBeInTheDocument()
  })
})

describe('AlbumWorkbench structure fallback', () => {
  const harness = new WorkbenchHarness()
  let fetchMock: FetchMockFn

  beforeEach(() => {
    fetchMock = harness.install()
  })

  afterEach(() => {
    harness.teardown()
  })

  it('shows structure fallback warning for loose folder imports', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${PREVIEW_JOB.id}`)) {
        return jsonResponse({
          ...PREVIEW_JOB,
          import_origin: 'folder',
          warnings: [
            'Folder is not a standard Arles album layout. Media was imported by filename only.',
          ],
          preview: {
            ...PREVIEW_JOB.preview!,
            structure_fallback: true,
          },
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    harness.renderWorkbench()

    expect(
      await screen.findByText(t.structureFallbackWarning),
    ).toBeInTheDocument()
    expect(document.querySelector('.workbench__structure-warning')).toBeTruthy()
  })

  it('redirects a folder hub parent to the first leaf album', async () => {
    const hubId = 'hub-parent'
    const leafId = 'leaf-aug10'
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith(`/api/jobs/${hubId}`) && (!url.includes('?') || url.includes('/api/jobs/'))) {
        return jsonResponse({
          id: hubId,
          status: 'waiting',
          type: 'preview',
          error: null,
          product_url: null,
          preview: null,
          preview_job_id: leafId,
          folder_label: 'Italy2012',
          child_ids: [leafId],
        } satisfies Job)
      }
      if (url.endsWith(`/api/jobs/${leafId}`)) {
        return jsonResponse(
          JobBuilder.preview({
            id: leafId,
            status: 'done',
            preview: {
              title: 'Aug10',
              description: null,
              multi_index: false,
              journal: null,
              items: [],
            },
          }).build(),
        )
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    const { router } = harness.renderWorkbench(hubId)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/albums/${leafId}`)
    })
  })
})
