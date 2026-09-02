import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { jobTypeLabel, t } from '../lib/language.ts'
import { JobChildBuilder, jsonResponse } from '../testing/index.ts'
import { affectedCancelJobLabel, CancelJobDialog } from './CancelJobDialog.tsx'

describe('CancelJobDialog', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows the simple cancel copy when there are no cancellable descendants', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ descendants: [] }))
    const onConfirm = vi.fn()

    render(
      <MemoryRouter>
        <CancelJobDialog open jobId="job-1" onCancel={() => undefined} onConfirm={onConfirm} />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('dialog', { name: t.confirmCancelJobTitle })).toBeInTheDocument()
    expect(screen.getByText(t.confirmCancelJobBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmCancelJobWithChildrenBody)).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: t.confirmCancelJobYes }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('lists descendant job links when cancel-preview returns children', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        descendants: [
          JobChildBuilder.scrape().build(),
          JobChildBuilder.preview().build(),
        ],
      }),
    )

    render(
      <MemoryRouter>
        <CancelJobDialog open jobId="hub-1" onCancel={() => undefined} onConfirm={() => undefined} />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.confirmCancelJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmCancelJobBody)).not.toBeInTheDocument()

    const scrapeLink = screen.getByRole('link', {
      name: t.jobsOpenAria(
        affectedCancelJobLabel({
          id: 'child-scrape',
          number: 8,
          type: 'scrape',
          scrape_url: 'https://albums.example/day2',
        }),
      ),
    })
    expect(scrapeLink).toHaveAttribute('href', '/jobs/child-scrape')
    expect(scrapeLink).toHaveTextContent('#8')
    expect(scrapeLink).toHaveTextContent(jobTypeLabel('scrape'))
    expect(scrapeLink).toHaveTextContent('https://albums.example/day2')

    const previewLink = screen.getByRole('link', {
      name: t.jobsOpenAria(
        affectedCancelJobLabel({
          id: 'child-preview',
          number: 9,
          type: 'preview',
          title: 'Day 2',
        }),
      ),
    })
    expect(previewLink).toHaveAttribute('href', '/jobs/child-preview')
    expect(previewLink).toHaveTextContent('Day 2')
    expect(previewLink).toHaveTextContent(jobTypeLabel('preview'))
  })

  it('falls back to the simple copy when cancel-preview fails', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

    render(
      <MemoryRouter>
        <CancelJobDialog open jobId="missing" onCancel={() => undefined} onConfirm={() => undefined} />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.confirmCancelJobBody)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText(t.confirmCancelJobWithChildrenBody)).not.toBeInTheDocument()
    })
  })
})
