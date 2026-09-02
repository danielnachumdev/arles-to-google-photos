import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { jobStatusLabel } from '../lib/language.ts'
import { JobStatusBadge } from './JobStatusBadge.tsx'

describe('JobStatusBadge', () => {
  it('uses overview colors for done, failed, and pending', () => {
    const { rerender } = render(<JobStatusBadge status="done" />)
    const done = screen.getByText(jobStatusLabel('done'))
    expect(done).toHaveClass('job-list__status', 'job-list__status--done')
    expect(done).not.toHaveAttribute('aria-busy')

    rerender(<JobStatusBadge status="failed" />)
    const failed = screen.getByText(jobStatusLabel('failed'))
    expect(failed).toHaveClass('job-list__status', 'job-list__status--failed')
    expect(failed).not.toHaveAttribute('aria-busy')

    rerender(<JobStatusBadge status="pending" />)
    const pending = screen.getByText(jobStatusLabel('pending'))
    expect(pending).toHaveClass('job-list__status', 'job-list__status--pending')
    expect(pending).not.toHaveAttribute('aria-busy')

    rerender(<JobStatusBadge status="cancelled" />)
    const cancelled = screen.getByText(jobStatusLabel('cancelled'))
    expect(cancelled).toHaveClass('job-list__status', 'job-list__status--cancelled')
    expect(cancelled).not.toHaveAttribute('aria-busy')
  })

  it('pulsates when running', () => {
    render(<JobStatusBadge status="running" />)
    const status = screen.getByText(jobStatusLabel('running'))
    expect(status).toHaveClass('job-list__status', 'job-list__status--running')
    expect(status).toHaveAttribute('aria-busy', 'true')
  })

  it('pulsates yellow when waiting', () => {
    render(<JobStatusBadge status="waiting" />)
    const status = screen.getByText(jobStatusLabel('waiting'))
    expect(status).toHaveClass('job-list__status', 'job-list__status--waiting')
    expect(status).not.toHaveClass('job-list__status--running')
    expect(status).toHaveAttribute('aria-busy', 'true')
  })
})
