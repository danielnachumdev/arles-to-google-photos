import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { t } from '../lib/language.ts'
import { ModifiedMark } from './ModifiedMark.tsx'

describe('ModifiedMark', () => {
  it('renders nothing when hidden', () => {
    const { container } = render(<ModifiedMark show={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the modified label when visible', () => {
    render(<ModifiedMark show />)
    expect(screen.getByText(t.modified)).toBeInTheDocument()
    expect(document.querySelector('.modified-mark')).toHaveAttribute('aria-hidden', 'true')
  })
})
