import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HintTooltip } from './HintTooltip.tsx'

const LABEL = 'How the concurrent job limit works'
const TEXT = 'Only running jobs count. Raising the limit starts pending jobs immediately.'

describe('HintTooltip', () => {
  it('reveals the hint on hover and hides it on leave', () => {
    render(<HintTooltip label={LABEL} text={TEXT} />)

    const trigger = screen.getByRole('button', { name: LABEL })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.mouseEnter(trigger)
    expect(screen.getByRole('tooltip')).toHaveTextContent(TEXT)

    fireEvent.mouseLeave(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('ignores Escape when the hint is already closed', () => {
    render(<HintTooltip label={LABEL} text={TEXT} />)

    const trigger = screen.getByRole('button', { name: LABEL })
    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('reveals the hint on focus and dismisses with Escape', () => {
    render(<HintTooltip label={LABEL} text={TEXT} />)

    const trigger = screen.getByRole('button', { name: LABEL })
    fireEvent.focus(trigger)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent(TEXT)
    expect(trigger).toHaveAttribute('aria-describedby', tooltip.id)

    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(trigger).not.toHaveAttribute('aria-describedby')
  })
})
