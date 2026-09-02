import { useId } from 'react'
import { t } from '../lib/language.ts'
import './HeaderFields.css'

export type HeaderRow = {
  id: string
  name: string
  value: string
}

let headerRowSeq = 0

export function createHeaderRow(name = '', value = ''): HeaderRow {
  headerRowSeq += 1
  return { id: `hdr-${headerRowSeq}`, name, value }
}

export function compactHeaderRows(rows: HeaderRow[]): Record<string, string> | undefined {
  const headers: Record<string, string> = {}
  for (const row of rows) {
    const name = row.name.trim()
    if (!name) {
      continue
    }
    headers[name] = row.value
  }
  return Object.keys(headers).length > 0 ? headers : undefined
}

export function HeaderFields({
  rows,
  onChange,
  disabled = false,
}: {
  rows: HeaderRow[]
  onChange: (rows: HeaderRow[]) => void
  disabled?: boolean
}) {
  const headingId = useId()

  function updateRow(id: string, patch: Partial<Pick<HeaderRow, 'name' | 'value'>>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  return (
    <div className="header-fields">
      <p className="header-fields__heading" id={headingId}>
        {t.webHeadersHeading}
      </p>
      <p className="header-fields__hint">{t.webHeadersHint}</p>
      {rows.length > 0 ? (
        <ul className="header-fields__list" aria-labelledby={headingId}>
          {rows.map((row, index) => (
            <li key={row.id} className="header-fields__row">
              <label className="header-fields__label">
                {t.headerNameLabel}
                <input
                  className="header-fields__input"
                  dir="ltr"
                  name={`header-name-${index}`}
                  value={row.name}
                  disabled={disabled}
                  autoComplete="off"
                  onChange={(event) => updateRow(row.id, { name: event.target.value })}
                />
              </label>
              <label className="header-fields__label">
                {t.headerValueLabel}
                <input
                  className="header-fields__input"
                  dir="ltr"
                  name={`header-value-${index}`}
                  value={row.value}
                  disabled={disabled}
                  autoComplete="off"
                  onChange={(event) => updateRow(row.id, { value: event.target.value })}
                />
              </label>
              <button
                type="button"
                className="header-fields__remove"
                disabled={disabled}
                onClick={() => onChange(rows.filter((item) => item.id !== row.id))}
              >
                {t.removeHeader}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <button
        type="button"
        className="header-fields__add"
        disabled={disabled}
        onClick={() => onChange([...rows, createHeaderRow()])}
      >
        {t.addHeader}
      </button>
    </div>
  )
}
