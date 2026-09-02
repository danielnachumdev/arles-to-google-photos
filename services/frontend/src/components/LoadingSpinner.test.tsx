import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoadingSpinner } from './LoadingSpinner.tsx'

describe('LoadingSpinner', () => {
  it('exposes a busy status with the label and spinner mark', () => {
    render(<LoadingSpinner label="Loading saved albums…" className="extra" />)

    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(status).toHaveClass('loading-spinner', 'extra')
    expect(screen.getByText('Loading saved albums…')).toBeInTheDocument()
    expect(status.querySelector('.loading-spinner__mark')).not.toBeNull()
  })
})
