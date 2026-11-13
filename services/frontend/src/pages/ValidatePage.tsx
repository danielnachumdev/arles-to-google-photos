import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import {
  compactHeaderRows,
  createHeaderRow,
  HeaderFields,
  type HeaderRow,
} from '../components/HeaderFields.tsx'
import { GoogleAuthCancelledError } from '../lib/googleAuth.ts'
import { explainCaughtError } from '../lib/formatApiError.ts'
import { t } from '../lib/language.ts'
import { announceRunSubmitted, kindFromJobType, trackRun } from '../lib/runTracker.ts'
import {
  readCacheHeadersToggle,
  readCachedImportHeaders,
  writeCachedImportHeaders,
} from '../lib/settings.ts'
import { withGooglePhotosAccessToken } from '../lib/withGooglePhotosToken.ts'
import './ValidatePage.css'

const client = new MigrationClient()

function initialHeaderRows(): HeaderRow[] {
  const cached = readCachedImportHeaders()
  if (cached) {
    return Object.entries(cached).map(([name, value]) => createHeaderRow(name, value))
  }
  return [createHeaderRow()]
}

export function ValidatePage() {
  const navigate = useNavigate()
  const urlId = useId()
  const [url, setUrl] = useState('')
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>(initialHeaderRows)
  const [cacheHeaders] = useState(() => readCacheHeadersToggle())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start() {
    const nextUrl = url.trim()
    if (!nextUrl || busy) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const headers = compactHeaderRows(headerRows)
      if (cacheHeaders && headers) {
        writeCachedImportHeaders(headers)
      }
      const created = await withGooglePhotosAccessToken((accessToken) =>
        client.createValidateJob({
          url: nextUrl,
          headers,
          access_token: accessToken,
        }),
      )
      announceRunSubmitted(created.id, created.number)
      trackRun({
        id: created.id,
        kind: kindFromJobType(created.type),
        status: created.status,
        error: created.error,
        number: created.number,
        scrape_url: created.scrape_url,
      })
      navigate(`/jobs/${created.id}`)
    } catch (err: unknown) {
      if (err instanceof GoogleAuthCancelledError) {
        setError(t.validateNeedsSignIn)
      } else {
        setError(explainCaughtError(err, t.errorValidate))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="validate-page">
      <div className="validate-page__stage">
        <h2 className="validate-page__heading">{t.validateHeading}</h2>
        <p className="validate-page__lede">{t.validateLede}</p>
        {error ? (
          <p className="validate-page__alert" role="alert" dir="auto">
            {error}
          </p>
        ) : null}
        <label className="validate-page__label" htmlFor={urlId}>
          {t.webUrlLabel}
        </label>
        <input
          id={urlId}
          className="validate-page__url"
          type="url"
          dir="ltr"
          placeholder="https://…"
          value={url}
          disabled={busy}
          onChange={(event) => setUrl(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void start()
            }
          }}
        />
        <p className="validate-page__hint">{t.webUrlHint}</p>
        <HeaderFields rows={headerRows} onChange={setHeaderRows} disabled={busy} />
        <div className="validate-page__actions">
          <button
            type="button"
            className="validate-page__submit"
            disabled={busy || url.trim().length === 0}
            onClick={() => void start()}
          >
            {busy ? t.validateStarting : t.validateStart}
          </button>
        </div>
      </div>
    </section>
  )
}
