import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { t } from '../lib/language.ts'
import {
  compactHeaderRows,
  createHeaderRow,
  HeaderFields,
  type HeaderRow,
} from './HeaderFields.tsx'

function Harness({ initial }: { initial?: HeaderRow[] }) {
  const [rows, setRows] = useState<HeaderRow[]>(initial ?? [createHeaderRow()])
  return <HeaderFields rows={rows} onChange={setRows} />
}

describe('compactHeaderRows', () => {
  it('keeps named rows and skips blank names', () => {
    expect(
      compactHeaderRows([
        { id: '1', name: 'Authorization', value: 'Bearer test-token' },
        { id: '2', name: '  ', value: 'ignored' },
        { id: '3', name: 'X-Test-Header', value: 'fixture-value' },
      ]),
    ).toEqual({
      Authorization: 'Bearer test-token',
      'X-Test-Header': 'fixture-value',
    })
  })

  it('returns undefined when no named headers remain', () => {
    expect(compactHeaderRows([{ id: '1', name: '', value: 'x' }])).toBeUndefined()
  })
})

describe('HeaderFields', () => {
  it('edits name/value rows and can add or remove them', () => {
    render(<Harness />)

    fireEvent.change(screen.getByLabelText(t.headerNameLabel), {
      target: { value: 'X-Test-Header' },
    })
    fireEvent.change(screen.getByLabelText(t.headerValueLabel), {
      target: { value: 'fixture-value' },
    })
    expect(screen.getByLabelText(t.headerNameLabel)).toHaveValue('X-Test-Header')
    expect(screen.getByLabelText(t.headerValueLabel)).toHaveValue('fixture-value')

    fireEvent.click(screen.getByRole('button', { name: t.addHeader }))
    expect(screen.getAllByLabelText(t.headerNameLabel)).toHaveLength(2)

    fireEvent.click(screen.getAllByRole('button', { name: t.removeHeader })[0]!)
    expect(screen.getAllByLabelText(t.headerNameLabel)).toHaveLength(1)
    expect(screen.getByLabelText(t.headerNameLabel)).toHaveValue('')
  })
})
