import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog.tsx'

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        message="Leave this page?"
        cancelLabel="Stay"
        confirmLabel="Leave"
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows title, message, and actions when open', () => {
    render(
      <ConfirmDialog
        open
        title="Delete album?"
        message="Only the backend job is removed."
        cancelLabel="Cancel"
        confirmLabel="Delete"
        danger
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )

    const dialog = screen.getByRole('dialog', { name: 'Delete album?' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveTextContent('Only the backend job is removed.')
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveClass(
      'confirm-dialog__confirm--danger',
    )
  })

  it('cancels from the cancel control, backdrop, and Escape', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        message="Discard edits?"
        cancelLabel="Keep editing"
        confirmLabel="Discard"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(onCancel).toHaveBeenCalledTimes(1)

    const backdrop = document.querySelector('.confirm-dialog__backdrop')
    expect(backdrop).toBeTruthy()
    fireEvent.click(backdrop!)
    expect(onCancel).toHaveBeenCalledTimes(2)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(3)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('confirms from the confirm control', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        message="Reprocess from stored files?"
        cancelLabel="Cancel"
        confirmLabel="Reprocess"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Reprocess' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('renders extra actions in the actions row', () => {
    render(
      <ConfirmDialog
        open
        title="Album exists"
        message="Overwrite the stored server job?"
        cancelLabel="Cancel"
        confirmLabel="Yes"
        extra={<a href="/albums/job-x">Open existing album</a>}
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )

    expect(screen.getByRole('link', { name: 'Open existing album' })).toHaveAttribute(
      'href',
      '/albums/job-x',
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Yes' })).toBeInTheDocument()
  })

  it('locks body scroll while open and restores it when closed', () => {
    document.body.style.overflow = 'auto'
    const { rerender } = render(
      <ConfirmDialog
        open
        message="Leave?"
        cancelLabel="Stay"
        confirmLabel="Leave"
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )
    expect(document.body.style.overflow).toBe('hidden')
    rerender(
      <ConfirmDialog
        open={false}
        message="Leave?"
        cancelLabel="Stay"
        confirmLabel="Leave"
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )
    expect(document.body.style.overflow).toBe('auto')
    document.body.style.overflow = ''
  })
})
