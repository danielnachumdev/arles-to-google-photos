import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { t } from '../lib/language.ts'
import { ReprocessConflictDialog } from './ReprocessConflictDialog.tsx'

describe('ReprocessConflictDialog', () => {
  it('renders cancel, overwrite, create new, and an editable prefix', () => {
    const onCancel = vi.fn()
    const onOverwrite = vi.fn()
    const onCreateNew = vi.fn()
    render(
      <ReprocessConflictDialog
        open
        unsaved
        saved
        onCancel={onCancel}
        onOverwrite={onOverwrite}
        onCreateNew={onCreateNew}
      />,
    )

    const dialog = screen.getByRole('dialog', { name: t.confirmReprocessConflictTitle })
    expect(dialog).toHaveTextContent(t.confirmReprocessConflictBody)
    expect(dialog).toHaveTextContent(t.confirmReprocessConflictUnsaved)
    expect(dialog).toHaveTextContent(t.confirmReprocessConflictSaved)
    expect(screen.queryByText(t.confirmReprocessConflictWeb)).not.toBeInTheDocument()

    const prefix = screen.getByLabelText(t.confirmReprocessPrefixLabel)
    expect(prefix).toHaveValue(t.reprocessTitlePrefix)
    fireEvent.change(prefix, { target: { value: 'Copy · ' } })

    fireEvent.click(screen.getByRole('button', { name: t.confirmCancel }))
    expect(onCancel).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: t.confirmReprocessOverwrite }))
    expect(onOverwrite).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: t.confirmReprocessCreateNew }))
    expect(onCreateNew).toHaveBeenCalledWith('Copy · ')
  })

  it('mentions a web re-download when web is true', () => {
    render(
      <ReprocessConflictDialog
        open
        web
        onCancel={() => undefined}
        onOverwrite={() => undefined}
        onCreateNew={() => undefined}
      />,
    )
    expect(screen.getByText(t.confirmReprocessConflictWeb)).toBeInTheDocument()
  })
})
