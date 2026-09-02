import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import type { JobSummary } from '../api/types.ts'
import { ConfirmDialog } from '../components/ConfirmDialog.tsx'
import { LoadingSpinner } from '../components/LoadingSpinner.tsx'
import { explainCaughtError } from '../lib/formatApiError.ts'
import { filterJobs } from '../lib/jobSearch.ts'
import { APP_LANGUAGE, t } from '../lib/language.ts'
import './AlbumLibrary.css'

const client = new MigrationClient()

function formatJobDate(iso: string | null | undefined): string {
  if (!iso) {
    return t.missingValue
  }
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    return t.missingValue
  }
  return parsed.toLocaleString(APP_LANGUAGE === 'he' ? 'he-IL' : 'en-US')
}

function albumTitle(item: JobSummary): string {
  return item.title?.trim() || item.folder_label?.trim() || t.untitledAlbum
}

function isSavedAlbum(item: JobSummary): boolean {
  if (item.type === 'scrape') {
    return false
  }
  return Boolean(item.title?.trim())
}

export function AlbumLibrary() {
  const searchId = useId()
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  useEffect(() => {
    void client
      .listJobs({ dedupe: true })
      .then((next) => {
        setJobs(next.filter(isSavedAlbum))
        setError(null)
      })
      .catch((err: unknown) => {
        setError(explainCaughtError(err, t.errorHistory))
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  async function confirmDelete() {
    const jobId = pendingDeleteId
    if (!jobId) {
      return
    }
    setPendingDeleteId(null)
    setDeletingId(jobId)
    setError(null)
    try {
      await client.deleteJob(jobId)
      setJobs((prev) => prev.filter((job) => job.id !== jobId))
    } catch (err: unknown) {
      setError(explainCaughtError(err, t.errorDelete))
    } finally {
      setDeletingId(null)
    }
  }

  const visible = filterJobs(jobs, query)

  return (
    <section className="album-library">
      <div className="album-library__stage">
        <h2 className="album-library__heading">{t.libraryHeading}</h2>
        <p className="album-library__lede">{t.libraryLede}</p>
        <label className="album-library__search-label" htmlFor={searchId}>
          {t.searchLabel}
          <input
            id={searchId}
            className="album-library__search"
            type="search"
            value={query}
            placeholder={t.searchPlaceholder}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        {error ? (
          <p className="album-library__error" role="alert" dir="auto">
            {error}
          </p>
        ) : null}
        {loading ? <LoadingSpinner label={t.loadingAlbums} /> : null}
        {!loading && jobs.length === 0 && !error ? (
          <p className="album-library__empty">{t.historyEmpty}</p>
        ) : null}
        {!loading && jobs.length > 0 && visible.length === 0 ? (
          <p className="album-library__empty">{t.libraryNoMatches}</p>
        ) : null}
        {!loading && visible.length > 0 ? (
          <ul className="library-list">
            {visible.map((item) => {
              const title = albumTitle(item)
              return (
                <li key={item.id} className="library-item">
                  <div className="library-item__head">
                    <Link
                      to={`/albums/${item.id}`}
                      className="library-item__open"
                      aria-label={t.historyOpenAria(title)}
                    >
                      <span className="library-item__title" dir="auto">
                        {title}
                      </span>
                    </Link>
                    <div className="library-item__actions">
                      <Link to={`/jobs/${item.id}`} className="library-item__job">
                        {t.viewJob}
                      </Link>
                      {item.product_url ? (
                        <a
                          className="library-item__photos"
                          href={item.product_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {t.openPhotosAlbum}
                        </a>
                      ) : null}
                      <button
                        type="button"
                        className="library-item__delete"
                        disabled={deletingId === item.id}
                        onClick={() => setPendingDeleteId(item.id)}
                      >
                        {deletingId === item.id ? t.deleting : t.deleteAlbum}
                      </button>
                    </div>
                  </div>
                  <div className="library-item__meta">
                    {item.folder_label ? (
                      <span className="library-item__folder" dir="auto">
                        {item.folder_label}
                      </span>
                    ) : null}
                    <span>{formatJobDate(item.created_at)}</span>
                    <span className="library-item__status" dir="ltr">
                      {item.status}
                    </span>
                    <span>{t.historyPhotoCount(item.item_count)}</span>
                  </div>
                </li>
              )
            })}
          </ul>
        ) : null}
      </div>
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t.confirmDeleteAlbumTitle}
        message={
          <ul>
            <li>{t.confirmDeleteAlbumServer}</li>
            <li>{t.confirmDeleteAlbumLocal}</li>
            <li>{t.confirmDeleteAlbumPhotos}</li>
          </ul>
        }
        cancelLabel={t.confirmCancel}
        confirmLabel={t.deleteAlbum}
        danger
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => void confirmDelete()}
      />
    </section>
  )
}
