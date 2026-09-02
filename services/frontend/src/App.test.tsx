import '@testing-library/jest-dom/vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Job } from './api/types.ts'
import { jobStatusLabel, jobTypeLabel, t } from './lib/language.ts'
import { jobToastLabel } from './lib/runTracker.ts'
import { getToasts } from './lib/toast.ts'
import {
  AlbumPreviewBuilder,
  ConfirmDialogInteractor,
  DiscardChangesInteractor,
  FakeAlbumFiles,
  JobBuilder,
  JobEventBuilder,
  JobSummaryBuilder,
  PreviewItemBuilder,
  ReprocessDialogInteractor,
  RoutedPageTestBase,
  SAMPLE_SETTINGS,
  jsonResponse,
  type FetchMockFn,
  type ScriptedFetchStrategy,
} from './testing/index.ts'

const SUMMER = JobSummaryBuilder.summer().build()
const WINTER = JobSummaryBuilder.winter().build()
const SUMMER_JOB = JobBuilder.summer().build()
const SCRAPE_ID = 'scrape-created-1'
const SCRAPE_JOB = JobBuilder.scrape().withId(SCRAPE_ID).build()
const CREATED_ID = 'f47ac10b-58cc-4372-a567-0e02b2c3d479'
const CREATED_JOB = JobBuilder.preview({
  id: CREATED_ID,
  folder_label: 'Day1',
  preview: AlbumPreviewBuilder.empty({
    title: 'אלבום חדש',
    items: [PreviewItemBuilder.jpeg().build()],
  }).build(),
}).build()

class AppRoutesHarness extends RoutedPageTestBase {
  protected override configureFetch(strategy: ScriptedFetchStrategy): void {
    strategy.on((request) => {
      if (request.path.endsWith('/api/settings') || request.path === '/api/settings') {
        return jsonResponse(SAMPLE_SETTINGS)
      }
      if (request.path.endsWith('/api/jobs') || request.path === '/api/jobs') {
        if (request.method === 'POST') {
          return jsonResponse(CREATED_JOB, 201)
        }
        return jsonResponse({ jobs: [SUMMER, WINTER] })
      }
      if (request.path.endsWith('/history')) {
        return jsonResponse({
          events: [
            JobEventBuilder.ingest().build(),
            JobEventBuilder.previewReady().build(),
          ],
        })
      }
      if (request.url.includes(`/api/jobs/${CREATED_ID}`)) {
        return jsonResponse(CREATED_JOB)
      }
      if (request.url.includes('/api/jobs/job-summer')) {
        if (request.method === 'POST' && request.url.endsWith('/reprocess')) {
          return jsonResponse({
            ...SUMMER_JOB,
            preview: {
              ...SUMMER_JOB.preview!,
              title: 'קיץ מעובד מחדש',
            },
          })
        }
        if (request.method === 'PATCH') {
          const body = JSON.parse(String(request.init?.body ?? '{}')) as {
            title?: string
            description?: string
            journal?: { heading: string | null; paragraphs: string[] }
            captions?: Record<string, string>
          }
          return jsonResponse({
            ...SUMMER_JOB,
            preview: {
              ...SUMMER_JOB.preview!,
              title: body.title ?? SUMMER_JOB.preview!.title,
              description: body.description ?? SUMMER_JOB.preview!.description,
              journal: body.journal ?? SUMMER_JOB.preview!.journal,
              items: SUMMER_JOB.preview!.items.map((item) => ({
                ...item,
                caption: body.captions?.[item.id] ?? item.caption,
              })),
            },
          })
        }
        return jsonResponse(SUMMER_JOB)
      }
      return null
    })
  }
}

function pickDay1Folder(): void {
  fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  const files = FakeAlbumFiles.day1Index()
  FakeAlbumFiles.assignToInput(input, files)
  fireEvent.change(input, { target: { files } })
}

describe('App routes', () => {
  const harness = new AppRoutesHarness()
  let fetchMock: FetchMockFn

  beforeEach(() => {
    fetchMock = harness.install()
  })

  afterEach(() => {
    harness.teardown()
  })

  it('home has folder upload by default and does not dump the full album history', async () => {
    const { router } = harness.renderApp('/')

    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByText(t.lede)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openAlbumLibrary })).toHaveAttribute('href', '/albums')
    expect(screen.getByRole('heading', { name: t.folderHeading })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.preparePreview })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: t.importModeUpload })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: t.autoPublishLabel })).toBeChecked()
    expect(screen.queryByRole('heading', { name: t.libraryHeading })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(t.searchLabel)).not.toBeInTheDocument()
    expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    expect(screen.queryByText('חורף 2019')).not.toBeInTheDocument()
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).split('?')[0] === '/api/jobs'),
      ).toBe(true)
    })
    expect(getToasts()).toEqual([])
  })

  it('albums page lists saved jobs with search, not a workbench preview', async () => {
    const { router } = harness.renderApp('/albums')

    expect(router.state.location.pathname).toBe('/albums')
    expect(await screen.findByRole('heading', { name: t.libraryHeading })).toBeInTheDocument()
    expect(screen.getByLabelText(t.searchLabel)).toBeInTheDocument()
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: t.folderHeading })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.preparePreview })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.save })).not.toBeInTheDocument()
  })

  it('album page shows only that album and keeps header nav', async () => {
    const { router } = harness.renderApp('/albums/job-summer')

    expect(router.state.location.pathname).toBe('/albums/job-summer')
    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    expect(screen.getByLabelText(t.journalHeadingLabel)).toHaveValue('יומן קיץ')
    expect(screen.getByRole('button', { name: t.save })).toBeDisabled()
    expect(screen.getByRole('button', { name: t.reprocess })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.reupload })).toBeEnabled()
    expect(screen.queryByText('חורף 2019')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: t.libraryHeading })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(t.searchLabel)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: t.folderHeading })).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: t.navAria })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.backToAlbums })).toHaveAttribute('href', '/albums')
    expect(screen.getByRole('link', { name: t.viewJob })).toHaveAttribute('href', '/jobs/job-summer')
    expect(screen.getByRole('link', { name: t.navAlbums })).not.toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: t.navHome })).not.toHaveAttribute('aria-current', 'page')
    await waitFor(() => {
      expect(document.title).toBe(t.albumDocumentTitle('קיץ 2012'))
    })
  })

  it('restores document title when leaving an album page', async () => {
    const { unmount } = harness.renderApp('/albums/job-summer')
    await screen.findByLabelText(t.titleLabel)
    expect(document.title).toBe(t.albumDocumentTitle('קיץ 2012'))
    unmount()
    expect(document.title).toBe(t.documentTitle)
  })

  it('creates a job from home and navigates to /albums/:jobId', async () => {
    const { router } = harness.renderApp('/')

    pickDay1Folder()

    const prepare = screen.getByRole('button', { name: t.preparePreview })
    await waitFor(() => expect(prepare).toBeEnabled())
    fireEvent.click(prepare)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/albums/${CREATED_ID}`)
    })
    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('אלבום חדש')
    expect(screen.queryByRole('heading', { name: t.folderHeading })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/jobs',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/jobs/${CREATED_ID}`,
      expect.objectContaining({ method: 'GET' }),
    )
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunSubmitted(jobToastLabel(CREATED_ID, CREATED_JOB.number)),
            href: `/jobs/${CREATED_ID}`,
            linkLabel: t.toastOpenRun,
          }),
          expect.objectContaining({
            type: 'good',
            message: t.toastPreviewDone(CREATED_ID),
            href: `/jobs/${CREATED_ID}`,
            linkLabel: t.toastOpenRun,
          }),
        ]),
      )
    })
    const runLinks = screen.getAllByRole('link', { name: t.toastOpenRun })
    expect(runLinks.length).toBeGreaterThan(0)
    expect(runLinks.every((link) => link.getAttribute('href') === `/jobs/${CREATED_ID}`)).toBe(
      true,
    )
  })

  it('imports from the web and navigates to the scrape job detail', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.split('?')[0]
      if (path.endsWith('/api/jobs/scrape') && method === 'POST') {
        return jsonResponse(SCRAPE_JOB, 201)
      }
      if (path.endsWith('/history') || path.endsWith('/children')) {
        return jsonResponse(path.endsWith('/children') ? { children: [] } : { events: [] })
      }
      if (url.includes(`/api/jobs/${SCRAPE_ID}`)) {
        return jsonResponse(SCRAPE_JOB)
      }
      if (path.endsWith('/api/jobs') || path === '/api/jobs') {
        if (method === 'POST') {
          return jsonResponse(CREATED_JOB, 201)
        }
        return jsonResponse({ jobs: [SUMMER, WINTER] })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    const { router } = harness.renderApp('/')
    fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.change(screen.getByLabelText(t.headerNameLabel), {
      target: { value: 'X-Test-Header' },
    })
    fireEvent.change(screen.getByLabelText(t.headerValueLabel), {
      target: { value: 'fixture-value' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/jobs/${SCRAPE_ID}`)
    })
    const scrapeCall = fetchMock.mock.calls.find((call) => String(call[0]) === '/api/jobs/scrape')
    expect(scrapeCall).toBeTruthy()
    expect(JSON.parse(String((scrapeCall![1] as RequestInit).body))).toEqual({
      url: 'https://gallery.example/index.html',
      headers: { 'X-Test-Header': 'fixture-value' },
    })
    expect(await screen.findByRole('heading', { name: t.jobDetailHeading })).toBeInTheDocument()
    expect(await screen.findByText(jobTypeLabel('scrape'))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://gallery.example/index.html' })).toHaveAttribute(
      'href',
      'https://gallery.example/index.html',
    )
    await waitFor(() => {
      expect(getToasts()).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'regular',
            message: t.toastRunSubmitted(jobToastLabel(SCRAPE_ID, SCRAPE_JOB.number)),
            href: `/jobs/${SCRAPE_ID}`,
            linkLabel: t.toastOpenRun,
          }),
        ]),
      )
    })
  })

  it('opening a library row navigates to that album URL', async () => {
    const { router } = harness.renderApp('/albums')

    expect(router.state.location.pathname).toBe('/albums')
    expect(screen.getByRole('link', { name: t.navAlbums })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(await screen.findByRole('link', { name: t.historyOpenAria('קיץ 2012') }))

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/albums/job-summer')
    })
    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    expect(screen.getByRole('link', { name: t.navAlbums })).not.toHaveAttribute('aria-current', 'page')
  })

  it('jobs page lists status and does not open the album editor', async () => {
    const { router } = harness.renderApp('/jobs')

    expect(router.state.location.pathname).toBe('/jobs')
    expect(screen.getByRole('link', { name: t.navJobs })).toHaveAttribute('aria-current', 'page')
    expect(await screen.findByRole('heading', { name: t.jobsHeading })).toBeInTheDocument()
    expect(screen.getAllByText(jobStatusLabel('done')).length).toBeGreaterThan(0)
    expect(screen.getByText('job-summer')).toBeInTheDocument()
    expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'אלבום' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Album link' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'קישור לאלבום' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openAlbum })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: t.photosHeading })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Photos URL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Google Photos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t.openPhotosAlbum })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.save })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(t.titleLabel)).not.toBeInTheDocument()
  })

  it('job detail shows run history instead of the album editor', async () => {
    const { router } = harness.renderApp('/jobs/job-summer')

    expect(router.state.location.pathname).toBe('/jobs/job-summer')
    expect(await screen.findByRole('heading', { name: t.runHistoryHeading })).toBeInTheDocument()
    expect(screen.getByText(jobStatusLabel('done'))).toBeInTheDocument()
    expect(screen.getByText('Writing upload')).toBeInTheDocument()
    expect(screen.queryByLabelText(t.titleLabel)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.save })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.openAlbum })).toHaveAttribute('href', '/albums/job-summer')
    expect(screen.getByRole('link', { name: t.backToJobs })).toHaveAttribute('href', '/jobs')
  })

  it('enables Save after an edit and disables it again after a successful save', async () => {
    harness.renderApp('/albums/job-summer')

    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    const save = screen.getByRole('button', { name: t.save })
    expect(save).toBeDisabled()

    fireEvent.change(screen.getByLabelText(t.titleLabel), { target: { value: 'קיץ מעודכן' } })
    expect(screen.getByRole('button', { name: t.save })).toBeEnabled()
    expect(screen.getByText(t.modified)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: t.save }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: t.save })).toBeDisabled()
    })
    expect(screen.getByLabelText(t.titleLabel)).toHaveValue('קיץ מעודכן')
    expect(screen.queryByText(t.modified)).not.toBeInTheDocument()

    const patchCall = fetchMock.mock.calls.find((call) => {
      const init = call[1] as RequestInit | undefined
      return init?.method === 'PATCH'
    })
    expect(patchCall).toBeTruthy()
  })

  it('blocks in-app navigation while dirty until discard is confirmed', async () => {
    harness.renderApp('/albums/job-summer')
    const discard = new DiscardChangesInteractor()

    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    fireEvent.change(screen.getByLabelText(t.titleLabel), { target: { value: 'טיוטה' } })

    fireEvent.click(screen.getByRole('link', { name: t.navAlbums }))
    discard.expectOpen()
    expect(screen.getByLabelText(t.titleLabel)).toHaveValue('טיוטה')
    expect(screen.queryByRole('heading', { name: t.libraryHeading })).not.toBeInTheDocument()

    discard.stay()
    discard.expectClosed()
    expect(screen.getByLabelText(t.titleLabel)).toHaveValue('טיוטה')

    fireEvent.click(screen.getByRole('link', { name: t.backToAlbums }))
    discard.expectOpen()
    discard.leave()

    expect(await screen.findByRole('heading', { name: t.libraryHeading })).toBeInTheDocument()
    expect(screen.queryByLabelText(t.titleLabel)).not.toBeInTheDocument()
  })

  it('asks in-app before overwriting an existing album and stays on home if cancelled', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.split('?')[0]
      if (path.endsWith('/api/jobs') && method === 'POST') {
        if (url.includes('overwrite=true')) {
          throw new Error('overwrite should not be requested after cancel')
        }
        return jsonResponse(
          {
            detail: {
              code: 'album_exists',
              existing_id: 'job-x',
              title: 'קיץ 2012',
            },
          },
          409,
        )
      }
      return jsonResponse({ jobs: [SUMMER, WINTER] })
    })

    const { router } = harness.renderApp('/')
    pickDay1Folder()

    const prepare = screen.getByRole('button', { name: t.preparePreview })
    await waitFor(() => expect(prepare).toBeEnabled())
    fireEvent.click(prepare)

    const overwrite = new ConfirmDialogInteractor(t.confirmOverwriteAlbumTitle('קיץ 2012'))
    const dialog = await overwrite.wait()
    expect(dialog).toHaveTextContent(t.confirmOverwriteAlbumBody)
    expect(screen.getByRole('link', { name: t.openExistingAlbum })).toHaveAttribute(
      'href',
      '/albums/job-x',
    )
    expect(router.state.location.pathname).toBe('/')

    overwrite.cancel()

    overwrite.expectClosed()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.getByRole('heading', { name: t.folderHeading })).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes('overwrite=true')),
    ).toBe(false)
  })

  it('overwrites the stored job after confirm and navigates to it', async () => {
    const overwritten: Job = { ...SUMMER_JOB, id: 'job-x', status: 'done', type: 'preview' }
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.split('?')[0]
      if (path.endsWith('/api/jobs') && method === 'POST') {
        if (url.includes('overwrite=true')) {
          return jsonResponse(overwritten, 201)
        }
        return jsonResponse(
          {
            detail: {
              code: 'album_exists',
              existing_id: 'job-x',
              title: 'קיץ 2012',
            },
          },
          409,
        )
      }
      if (url.includes('/api/jobs/job-x')) {
        return jsonResponse(overwritten)
      }
      return jsonResponse({ jobs: [SUMMER, WINTER] })
    })

    const { router } = harness.renderApp('/')
    pickDay1Folder()

    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    const overwrite = new ConfirmDialogInteractor(t.confirmOverwriteAlbumTitle('קיץ 2012'))
    await overwrite.wait()
    overwrite.confirm(t.confirmOverwriteAlbumYes)

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/albums/job-x')
    })
    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    expect(
      fetchMock.mock.calls.some((call) => {
        const requestUrl = String(call[0])
        const init = call[1] as RequestInit | undefined
        return requestUrl === '/api/jobs?overwrite=true' && init?.method === 'POST'
      }),
    ).toBe(true)
  })

  it('shows an error if overwrite ingest fails', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const path = url.split('?')[0]
      if (path.endsWith('/api/jobs') && method === 'POST') {
        if (url.includes('overwrite=true')) {
          return jsonResponse({ detail: 'disk full' }, 500)
        }
        return jsonResponse(
          {
            detail: {
              code: 'album_exists',
              existing_id: 'job-x',
              title: 'קיץ 2012',
            },
          },
          409,
        )
      }
      return jsonResponse({ jobs: [SUMMER, WINTER] })
    })

    harness.renderApp('/')
    pickDay1Folder()

    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    const overwrite = new ConfirmDialogInteractor(t.confirmOverwriteAlbumTitle('קיץ 2012'))
    await overwrite.wait()
    overwrite.confirm(t.confirmOverwriteAlbumYes)

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errorOverwrite('HTTP 500: disk full'))
    expect(screen.getByRole('heading', { name: t.folderHeading })).toBeInTheDocument()
  })

  it('asks in-app before reprocess and skips the request on cancel', async () => {
    harness.renderApp('/albums/job-summer')
    const reprocess = new ReprocessDialogInteractor()

    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    fireEvent.click(screen.getByRole('button', { name: t.reprocess }))

    reprocess.expectOpen()
    reprocess.cancel()

    reprocess.expectClosed()
    expect(screen.getByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes('/reprocess')),
    ).toBe(false)
  })

  it('reprocesses from stored files after confirm', async () => {
    harness.renderApp('/albums/job-summer')
    const reprocess = new ReprocessDialogInteractor()

    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    fireEvent.click(screen.getByRole('button', { name: t.reprocess }))

    reprocess.expectOpen()
    reprocess.confirm(t.reprocess)

    await waitFor(() => {
      expect(screen.getByLabelText(t.titleLabel)).toHaveValue('קיץ מעובד מחדש')
    })
    expect(
      fetchMock.mock.calls.some((call) => {
        const url = String(call[0])
        const init = call[1] as RequestInit | undefined
        return url.endsWith('/api/jobs/job-summer/reprocess') && init?.method === 'POST'
      }),
    ).toBe(true)
    expect(getToasts()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          type: 'regular',
          message: t.toastRunSubmitted(jobToastLabel('job-summer', SUMMER_JOB.number)),
          href: '/jobs/job-summer',
          linkLabel: t.toastOpenRun,
        }),
      ]),
    )
  })

  it('does not prompt when leaving a pristine album', async () => {
    harness.renderApp('/albums/job-summer')

    expect(await screen.findByLabelText(t.titleLabel)).toHaveValue('קיץ 2012')
    fireEvent.click(screen.getByRole('link', { name: t.navAlbums }))

    expect(await screen.findByRole('heading', { name: t.libraryHeading })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: t.discardChanges })).not.toBeInTheDocument()
  })

  it('header navigates between new, albums, and jobs', async () => {
    harness.renderApp('/')

    expect(screen.getByRole('navigation', { name: t.navAria })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: t.navAlbums }))
    expect(await screen.findByLabelText(t.searchLabel)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: t.navJobs }))
    expect(await screen.findByRole('heading', { name: t.jobsHeading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.navJobs })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: t.navHome }))
    expect(screen.getByRole('heading', { name: t.folderHeading })).toBeInTheDocument()
    expect(screen.queryByLabelText(t.searchLabel)).not.toBeInTheDocument()
  })

  it('does not toast historical jobs on settings', async () => {
    harness.renderApp('/settings')

    expect(await screen.findByRole('heading', { name: t.settingsHeading })).toBeInTheDocument()
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).split('?')[0] === '/api/jobs'),
      ).toBe(true)
    })
    expect(getToasts()).toEqual([])
  })

  it('header has a settings link that opens the settings page', () => {
    const { router } = harness.renderApp('/')

    const settings = screen.getByRole('link', { name: t.navSettings })
    expect(settings).toHaveAttribute('href', '/settings')
    fireEvent.click(settings)

    expect(router.state.location.pathname).toBe('/settings')
    expect(screen.getByRole('heading', { name: t.settingsHeading })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.navSettings })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('unknown path shows the not-found page', async () => {
    const { router } = harness.renderApp('/this-route-does-not-exist')

    expect(router.state.location.pathname).toBe('/this-route-does-not-exist')
    expect(await screen.findByRole('heading', { name: t.notFoundHeading })).toBeInTheDocument()
    expect(screen.getByText(t.notFoundLede)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.notFoundHome })).toHaveAttribute('href', '/')
    expect(screen.queryByRole('heading', { name: t.webImportHeading })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: t.libraryHeading })).not.toBeInTheDocument()
  })

  it('direct job link that the API reports missing shows the not-found page', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'job not found' }, 404))

    const { router } = harness.renderApp('/jobs/other-users-job')

    expect(router.state.location.pathname).toBe('/jobs/other-users-job')
    expect(await screen.findByRole('heading', { name: t.notFoundHeading })).toBeInTheDocument()
    expect(screen.getByText(t.notFoundLede)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: t.jobDetailHeading })).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('direct album link that the API reports missing shows the not-found page', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'job not found' }, 404))

    const { router } = harness.renderApp('/albums/other-users-album')

    expect(router.state.location.pathname).toBe('/albums/other-users-album')
    expect(await screen.findByRole('heading', { name: t.notFoundHeading })).toBeInTheDocument()
    expect(screen.getByText(t.notFoundLede)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.titleLabel)).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
