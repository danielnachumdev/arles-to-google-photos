import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { jobStatusLabel, jobTypeLabel, t } from '../lib/language.ts'
import { JobChildBuilder, jsonResponse } from '../testing/index.ts'
import { affectedRestartJobLabel, RestartJobDialog } from './RestartJobDialog.tsx'

describe('RestartJobDialog', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows the simple restart copy when there are no scrape children', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ descendants: [], done: [], remaining: [] }),
    )
    const onConfirm = vi.fn()

    render(
      <MemoryRouter>
        <RestartJobDialog open jobId="job-1" onCancel={() => undefined} onConfirm={onConfirm} />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('dialog', { name: t.confirmRestartJobTitle })).toBeInTheDocument()
    expect(screen.getByText(t.confirmRestartJobBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmRestartJobWithChildrenBody)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.confirmRestartJobAll })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobYes }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onConfirm).toHaveBeenCalledWith('all')
  })

  it('lists remaining and done scrape children with All vs Remaining actions', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        descendants: [
          JobChildBuilder.scrape({
            id: 'child-done',
            number: 8,
            status: 'done',
            scrape_url: 'https://albums.example/day1',
          }).build(),
          JobChildBuilder.scrape({
            id: 'child-failed',
            number: 9,
            status: 'failed',
            scrape_url: 'https://albums.example/day2',
          }).build(),
        ],
        done: [
          JobChildBuilder.scrape({
            id: 'child-done',
            number: 8,
            status: 'done',
            scrape_url: 'https://albums.example/day1',
          }).build(),
        ],
        remaining: [
          JobChildBuilder.scrape({
            id: 'child-failed',
            number: 9,
            status: 'failed',
            scrape_url: 'https://albums.example/day2',
          }).build(),
        ],
      }),
    )
    const onConfirm = vi.fn()

    render(
      <MemoryRouter>
        <RestartJobDialog open jobId="hub-1" onCancel={() => undefined} onConfirm={onConfirm} />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.confirmRestartJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.queryByText(t.confirmRestartJobBody)).not.toBeInTheDocument()
    expect(screen.getByText(t.confirmRestartJobRemainingHeading)).toBeInTheDocument()
    expect(screen.getByText(t.confirmRestartJobDoneHeading)).toBeInTheDocument()

    const remainingLink = screen.getByRole('link', {
      name: t.jobsOpenAria(
        affectedRestartJobLabel({
          id: 'child-failed',
          number: 9,
          status: 'failed',
          type: 'scrape',
          scrape_url: 'https://albums.example/day2',
        }),
      ),
    })
    expect(remainingLink).toHaveAttribute('href', '/jobs/child-failed')
    expect(remainingLink).toHaveTextContent('#9')
    expect(remainingLink).toHaveTextContent(jobTypeLabel('scrape'))
    expect(remainingLink).toHaveTextContent(jobStatusLabel('failed'))

    const doneLink = screen.getByRole('link', {
      name: t.jobsOpenAria(
        affectedRestartJobLabel({
          id: 'child-done',
          number: 8,
          status: 'done',
          type: 'scrape',
          scrape_url: 'https://albums.example/day1',
        }),
      ),
    })
    expect(doneLink).toHaveAttribute('href', '/jobs/child-done')
    expect(doneLink).toHaveTextContent(jobStatusLabel('done'))

    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobRemaining }))
    expect(onConfirm).toHaveBeenCalledWith('remaining')

    onConfirm.mockClear()
    fireEvent.click(screen.getByRole('button', { name: t.confirmRestartJobAll }))
    expect(onConfirm).toHaveBeenCalledWith('all')
  })

  it('disables Remaining when every scrape child is done', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        descendants: [
          {
            id: 'child-done',
            number: 8,
            status: 'done',
            type: 'scrape',
            scrape_url: 'https://albums.example/day1',
          },
        ],
        done: [
          {
            id: 'child-done',
            number: 8,
            status: 'done',
            type: 'scrape',
            scrape_url: 'https://albums.example/day1',
          },
        ],
        remaining: [],
      }),
    )

    render(
      <MemoryRouter>
        <RestartJobDialog open jobId="hub-1" onCancel={() => undefined} onConfirm={() => undefined} />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.confirmRestartJobWithChildrenBody)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.confirmRestartJobRemaining })).toBeDisabled()
    expect(screen.getByRole('button', { name: t.confirmRestartJobAll })).toBeEnabled()
  })

  it('falls back to the simple copy when restart-preview fails', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'job not found' }, 404))

    render(
      <MemoryRouter>
        <RestartJobDialog open jobId="missing" onCancel={() => undefined} onConfirm={() => undefined} />
      </MemoryRouter>,
    )

    expect(await screen.findByText(t.confirmRestartJobBody)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText(t.confirmRestartJobWithChildrenBody)).not.toBeInTheDocument()
    })
  })
})
