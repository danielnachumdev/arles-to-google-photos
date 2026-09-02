import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JobSummary } from '../api/types.ts'
import { messages, t } from '../lib/language.ts'
import { ConfirmDialogInteractor, JobSummaryBuilder, jsonResponse } from '../testing/index.ts'
import { AlbumLibrary } from './AlbumLibrary.tsx'

const JOBS: JobSummary[] = [
  JobSummaryBuilder.summer().build(),
  JobSummaryBuilder.winter().build(),
  JobSummaryBuilder.scrapeHost().build(),
]

describe('AlbumLibrary', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/jobs')) {
        return jsonResponse({ jobs: JOBS })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('names saved albums in hebrew and english', () => {
    expect(messages.he.navAlbums).toBe('אלבומים שמורים')
    expect(messages.en.navAlbums).toBe('Saved albums')
    expect(messages.he.libraryHeading).toBe('אלבומים שמורים')
    expect(messages.en.libraryHeading).toBe('Saved albums')
    expect(messages.he.libraryLede).toMatch(/האתר החי/)
    expect(messages.en.libraryLede).toMatch(/live website/i)
    expect(messages.he.historyEmpty).toMatch(/אלבומים שמורים/)
    expect(messages.en.historyEmpty).toMatch(/saved albums/i)
    expect(messages.he.openAlbumLibrary).toMatch(/אלבומים שמורים/)
    expect(messages.en.openAlbumLibrary).toMatch(/saved albums/i)
    expect(messages.he.backToAlbums).toMatch(/אלבומים שמורים/)
    expect(messages.en.backToAlbums).toMatch(/saved albums/i)
    expect(messages.he.jobsLede).toMatch(/כל הרצה/)
    expect(messages.en.jobsLede).toMatch(/every run/i)
    expect(messages.he.lede).toMatch(/אלבומים שמורים/)
    expect(messages.en.lede).toMatch(/Saved albums/)
  })

  it('still shows a gallery card when the backing job run is archived', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/jobs')) {
        return jsonResponse({
          jobs: [
            JobSummaryBuilder.summer({
              archived_at: '2026-08-08T12:00:00+00:00',
            }).build(),
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    expect(await screen.findByText('קיץ 2012')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: t.historyOpenAria('קיץ 2012') }),
    ).toHaveAttribute('href', '/albums/job-summer')
    expect(screen.queryByText(t.historyEmpty)).not.toBeInTheDocument()
  })

  it('shows a spinner instead of empty until albums arrive', async () => {
    let resolveJobs: ((value: Response) => void) | undefined
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/jobs')) {
        return await new Promise<Response>((resolve) => {
          resolveJobs = resolve
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText(t.loadingAlbums)).toBeInTheDocument()
    expect(screen.queryByText(t.historyEmpty)).not.toBeInTheDocument()

    resolveJobs?.(jsonResponse({ jobs: JOBS }))

    expect(await screen.findByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByText(t.historyEmpty)).not.toBeInTheDocument()
  })

  it('shows saved-albums heading and lede, not scrape-only hostname rows', async () => {
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: t.libraryHeading })).toBeInTheDocument()
    expect(screen.getByText(t.libraryLede)).toBeInTheDocument()
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()
    expect(screen.getByText('Day1')).toBeInTheDocument()
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()
  })

  it('shows empty copy when only scrape-only jobs exist', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/jobs')) {
        return jsonResponse({
          jobs: [
            {
              id: 'job-scrape-only',
              status: 'done',
              type: 'scrape',
              error: null,
              title: 'albums.example',
              item_count: 0,
              created_at: '2026-08-08T00:00:00+00:00',
              product_url: null,
              folder_label: 'albums.example',
            } satisfies JobSummary,
          ],
        })
      }
      return jsonResponse({ detail: 'not found' }, 404)
    })

    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.historyEmpty)).toBeInTheDocument()
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()
  })

  it('filters listed albums by title, folder label, id, and status', async () => {
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    expect(await screen.findByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()
    expect(screen.queryByText('albums.example')).not.toBeInTheDocument()

    const search = screen.getByLabelText(t.searchLabel)

    fireEvent.change(search, { target: { value: 'קיץ' } })
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.queryByText('חורף 2019')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'SkiTrip' } })
    expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'job-summer' } })
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
    expect(screen.queryByText('חורף 2019')).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'preview' } })
    expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()
  })

  it('links each row to the single-album page', async () => {
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    const openSummer = await screen.findByRole('link', { name: t.historyOpenAria('קיץ 2012') })
    expect(openSummer).toHaveAttribute('href', '/albums/job-summer')
    expect(screen.getAllByRole('link', { name: t.viewJob })[0]).toHaveAttribute('href', '/jobs/job-summer')
  })

  it('keeps the album title on the same row as view-job and delete', async () => {
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    const openSummer = await screen.findByRole('link', { name: t.historyOpenAria('קיץ 2012') })
    const viewJob = screen.getAllByRole('link', { name: t.viewJob })[0]
    const deleteAlbum = screen.getAllByRole('button', { name: t.deleteAlbum })[0]

    expect(openSummer).toHaveTextContent('קיץ 2012')
    expect(openSummer).not.toHaveTextContent(t.viewJob)
    expect(openSummer).not.toHaveTextContent(t.historyPhotoCount(3))
    expect(openSummer.parentElement?.contains(viewJob)).toBe(true)
    expect(openSummer.parentElement?.contains(deleteAlbum)).toBe(true)
    expect(openSummer.contains(viewJob)).toBe(false)
  })

  it('keeps the row when delete confirm is cancelled', async () => {
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    await screen.findByText('קיץ 2012')
    fireEvent.click(screen.getAllByRole('button', { name: t.deleteAlbum })[0])

    const del = new ConfirmDialogInteractor(t.confirmDeleteAlbumTitle)
    const dialog = del.expectOpen()
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumServer)
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumLocal)
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumPhotos)
    del.cancel()

    del.expectClosed()
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.some((call) => (call[1] as RequestInit | undefined)?.method === 'DELETE'),
    ).toBe(false)
  })

  it('shows a history error when the library cannot load', async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: 'down' }, 503))
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(t.errorHistory('HTTP 503: down'))
  })

  it('shows missing dates and no-match search copy', async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        jobs: [JobSummaryBuilder.winter({ created_at: 'not-a-date' }).build()],
      }),
    )
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )
    expect(await screen.findByText('חורף 2019')).toBeInTheDocument()
    expect(screen.getByText(t.missingValue)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(t.searchLabel), { target: { value: 'zzzz' } })
    expect(screen.getByText(t.libraryNoMatches)).toBeInTheDocument()
  })

  it('shows a delete error when DELETE fails', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return Promise.resolve(jsonResponse({ detail: 'locked' }, 500))
      }
      return Promise.resolve(jsonResponse({ jobs: JOBS }))
    })
    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )
    await screen.findByText('קיץ 2012')
    fireEvent.click(screen.getAllByRole('button', { name: t.deleteAlbum })[0])
    new ConfirmDialogInteractor(t.confirmDeleteAlbumTitle).confirm(t.deleteAlbum)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errorDelete('HTTP 500: locked'),
    )
    expect(screen.getByText('קיץ 2012')).toBeInTheDocument()
  })

  it('calls DELETE and removes the title after confirm', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        expect(String(input)).toBe('/api/jobs/job-summer')
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse({ jobs: JOBS }))
    })

    render(
      <MemoryRouter>
        <AlbumLibrary />
      </MemoryRouter>,
    )

    await screen.findByText('קיץ 2012')
    fireEvent.click(screen.getAllByRole('button', { name: t.deleteAlbum })[0])

    const del = new ConfirmDialogInteractor(t.confirmDeleteAlbumTitle)
    const dialog = del.expectOpen()
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumServer)
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumLocal)
    expect(dialog).toHaveTextContent(t.confirmDeleteAlbumPhotos)
    del.confirm(t.deleteAlbum)

    await waitFor(() => {
      expect(screen.queryByText('קיץ 2012')).not.toBeInTheDocument()
    })
    expect(screen.getByText('חורף 2019')).toBeInTheDocument()
  })
})
