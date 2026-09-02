import { useEffect, useId, useState } from 'react'
import { t } from '../lib/language.ts'
import {
  readCacheHeadersToggle,
  readCachedImportHeaders,
  readDefaultImportMode,
  SETTINGS_CHANGED_EVENT,
  writeCacheHeadersToggle,
  writeCachedImportHeaders,
  type ImportModeSetting,
} from '../lib/settings.ts'
import {
  compactHeaderRows,
  createHeaderRow,
  HeaderFields,
  type HeaderRow,
} from './HeaderFields.tsx'
import './ImportDesk.css'

export type ImportMode = ImportModeSetting

function initialHeaderRows(): HeaderRow[] {
  const cached = readCachedImportHeaders()
  if (cached) {
    return Object.entries(cached).map(([name, value]) => createHeaderRow(name, value))
  }
  return [createHeaderRow()]
}

export function ImportDesk({
  busy,
  working,
  folderLabel,
  fileCount,
  folderInputId,
  onFolder,
  onPreparePreview,
  onImportWeb,
}: {
  busy: boolean
  working: boolean
  folderLabel: string
  fileCount: number
  folderInputId: string
  onFolder: (files: FileList | null) => void
  onPreparePreview: (autoPublish: boolean) => void
  onImportWeb: (url: string, headers?: Record<string, string>, autoPublish?: boolean) => void
}) {
  const modeName = useId()
  const urlId = useId()
  const autoPublishId = useId()
  const [mode, setMode] = useState<ImportMode>(() => readDefaultImportMode())
  const [autoPublish, setAutoPublish] = useState(true)
  const [url, setUrl] = useState('')
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>(initialHeaderRows)
  const [cacheHeaders, setCacheHeaders] = useState(() => readCacheHeadersToggle())

  useEffect(() => {
    function syncDefaultMode(): void {
      setMode(readDefaultImportMode())
    }
    window.addEventListener(SETTINGS_CHANGED_EVENT, syncDefaultMode)
    return () => {
      window.removeEventListener(SETTINGS_CHANGED_EVENT, syncDefaultMode)
    }
  }, [])

  const urlReady = url.trim().length > 0

  function submitWeb() {
    const nextUrl = url.trim()
    if (!nextUrl || busy) {
      return
    }
    const headers = compactHeaderRows(headerRows)
    if (cacheHeaders && headers) {
      writeCachedImportHeaders(headers)
    }
    onImportWeb(nextUrl, headers, autoPublish)
  }

  return (
    <div className="workbench__stage import-desk">
      <h2 className="workbench__stage-title">
        {mode === 'web' ? t.webImportHeading : t.folderHeading}
      </h2>
      <div className="import-mode" role="radiogroup" aria-label={t.importModeAria}>
        <label
          className={
            mode === 'upload' ? 'import-mode__choice import-mode__choice--active' : 'import-mode__choice'
          }
        >
          <input
            className="visually-hidden"
            type="radio"
            name={modeName}
            value="upload"
            checked={mode === 'upload'}
            onChange={() => setMode('upload')}
          />
          {t.importModeUpload}
        </label>
        <label
          className={
            mode === 'web' ? 'import-mode__choice import-mode__choice--active' : 'import-mode__choice'
          }
        >
          <input
            className="visually-hidden"
            type="radio"
            name={modeName}
            value="web"
            checked={mode === 'web'}
            onChange={() => setMode('web')}
          />
          {t.importModeWeb}
        </label>
      </div>

      <div className="import-desk__auto">
        <label className="import-desk__auto-row" htmlFor={autoPublishId}>
          <input
            id={autoPublishId}
            type="checkbox"
            checked={autoPublish}
            disabled={busy}
            onChange={(event) => setAutoPublish(event.target.checked)}
          />
          {t.autoPublishLabel}
        </label>
        <span className="workbench__hint">{t.autoPublishHint}</span>
      </div>

      {mode === 'upload' ? (
        <>
          <div className="folder-pick">
            <input
              id={folderInputId}
              className="visually-hidden"
              type="file"
              // @ts-expect-error non-standard directory picker
              webkitdirectory=""
              directory=""
              multiple
              onChange={(event) => onFolder(event.target.files)}
            />
            <label className="folder-pick__face" htmlFor={folderInputId}>
              <span className="folder-pick__name" dir="auto">
                {folderLabel || t.folderPickPlaceholder}
              </span>
              <span className="folder-pick__meta">
                {folderLabel ? (
                  t.fileCount(fileCount)
                ) : (
                  <>
                    {t.folderRequiredPrefix}{' '}
                    <span dir="ltr">{t.folderRequiredPaths}</span>
                  </>
                )}
              </span>
            </label>
            <button
              type="button"
              className="workbench__button"
              disabled={fileCount === 0 || busy}
              onClick={() => onPreparePreview(autoPublish)}
            >
              {working ? t.preparing : t.preparePreview}
            </button>
          </div>
          {!folderLabel ? <p className="workbench__invite">{t.folderInvite}</p> : null}
        </>
      ) : (
        <form
          className="web-import"
          onSubmit={(event) => {
            event.preventDefault()
            submitWeb()
          }}
        >
          <div className="workbench__field">
            <label className="workbench__label" htmlFor={urlId}>
              {t.webUrlLabel}
            </label>
            <span className="workbench__hint">{t.webUrlHint}</span>
            <input
              id={urlId}
              className="workbench__input"
              dir="ltr"
              type="url"
              name="gallery-url"
              value={url}
              placeholder="https://"
              autoComplete="url"
              disabled={busy}
              onChange={(event) => setUrl(event.target.value)}
            />
          </div>
          <div className="web-import__cache">
            <label className="web-import__cache-row">
              <input
                type="checkbox"
                checked={cacheHeaders}
                disabled={busy}
                onChange={(event) => {
                  const next = event.target.checked
                  setCacheHeaders(next)
                  writeCacheHeadersToggle(next)
                }}
              />
              {t.cacheHeadersLabel}
            </label>
            <span className="workbench__hint">{t.cacheHeadersHint}</span>
          </div>
          <HeaderFields rows={headerRows} onChange={setHeaderRows} disabled={busy} />
          <button
            type="submit"
            className="workbench__button"
            disabled={!urlReady || busy}
            onClick={(event) => {
              event.preventDefault()
              submitWeb()
            }}
          >
            {working ? t.importingWeb : t.startWebImport}
          </button>
          {!urlReady ? <p className="workbench__invite">{t.webInvite}</p> : null}
        </form>
      )}
    </div>
  )
}
