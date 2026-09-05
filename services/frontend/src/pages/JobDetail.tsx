import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import { JobEventSource } from '../api/events.ts'
import type { Job, JobChild, JobEvent, RestartMode } from '../api/types.ts'
import { CancelJobDialog } from '../components/CancelJobDialog.tsx'
import { RestartJobDialog } from '../components/RestartJobDialog.tsx'
import { JobStatusBadge } from '../components/JobStatusBadge.tsx'
import { LoadingSpinner } from '../components/LoadingSpinner.tsx'
import { GoogleAuthCancelledError } from '../lib/googleAuth.ts'
import { withGooglePhotosAccessToken } from '../lib/withGooglePhotosToken.ts'
import { formatJobDate } from '../lib/formatJobDate.ts'
import { explainCaughtError, isNotFoundError } from '../lib/formatApiError.ts'
import { isJobActive, isJobCancellable } from '../lib/formatJobDuration.ts'
import {
  formatLogTime,
  isLifecycleJobEvent,
  jobLogMessage,
  jobLogTone,
  shouldShowJobLog,
} from '../lib/jobLogs.ts'
import {
  childDisplayLabel,
  childHasAlbumDesk,
  jobDocumentLabel,
  jobErrorMessage,
  jobFolderLabel,
  jobGalleryTitle,
  jobPhotoCount,
  jobPhotosUrl,
  jobScrapeUrl,
} from '../lib/jobFields.ts'
import { APP_LANGUAGE, jobTypeLabel, t } from '../lib/language.ts'
import { announceRunSubmitted, kindFromJobType, trackRun } from '../lib/runTracker.ts'
import { NotFoundPage } from './NotFoundPage.tsx'
import './JobDetail.css'

const client = new MigrationClient()
const events = new JobEventSource()
const POLL_MS = 2500

function eventKey(event: JobEvent): string {
  return [
    event.occurred_at ?? '',
    event.stage,
    event.kind ?? '',
    event.audience ?? '',
    event.message,
    String(event.current),
    String(event.total),
  ].join('\0')
}

function eventEtaSeconds(event: JobEvent): number | null {
  const raw = event.extra?.eta_seconds
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return raw
  }
  if (typeof raw === 'string' && raw.trim() !== '') {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function previewChildId(job: Job, children: JobChild[]): string | null {
  if (job.preview_job_id) {
    return job.preview_job_id
  }
  const preview = children.find((child) => child.type === 'preview' || Boolean(child.preview))
  return preview?.id ?? null
}

function albumDeskHref(job: Job, children: JobChild[]): string | null {
  if (job.type === 'scrape') {
    if (job.status !== 'done') {
      return null
    }
    const childId = previewChildId(job, children)
    return childId ? `/albums/${childId}` : null
  }
  // Folder hub / parent preview with no local album: open first leaf.
  if (!job.preview) {
    const childId = previewChildId(job, children)
    return childId ? `/albums/${childId}` : null
  }
  return `/albums/${job.source_job_id ?? job.id}`
}

function headerItems(job: Job): Array<{ name: string; value?: string }> {
  if (job.headers && Object.keys(job.headers).length > 0) {
    return Object.entries(job.headers).map(([name, value]) => ({ name, value }))
  }
  return (job.header_names ?? []).map((name) => ({ name }))
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="job-detail__row">
      <dt className="job-detail__key">{label}</dt>
      <dd className="job-detail__value">{children}</dd>
    </div>
  )
}

function childIdsCovered(embedded: JobChild[], childIds: string[]): boolean {
  if (childIds.length === 0) {
    return embedded.length > 0
  }
  if (embedded.length < childIds.length) {
    return false
  }
  const have = new Set(embedded.map((child) => child.id))
  return childIds.every((id) => have.has(id))
}

async function resolveChildren(job: Job): Promise<JobChild[]> {
  const embedded = job.children ?? []
  const childIds = job.child_ids ?? []
  if (embedded.length > 0 && childIdsCovered(embedded, childIds)) {
    return embedded
  }
  try {
    const listed = await client.listJobChildren(job.id)
    if (listed.length > 0) {
      return listed
    }
  } catch {
    // fall through to child_ids from the job payload
  }
  if (childIds.length > 0) {
    return childIds.map((id) => ({ id }))
  }
  return embedded
}

async function loadChildren(job: Job, forceRefresh = false): Promise<JobChild[]> {
  if (forceRefresh) {
    try {
      const listed = await client.listJobChildren(job.id)
      if (listed.length > 0) {
        return listed
      }
    } catch {
      // fall through to resolveChildren
    }
  }
  return resolveChildren(job)
}

export function JobDetail({ jobId }: { jobId: string }) {
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [children, setChildren] = useState<JobChild[]>([])
  const [history, setHistory] = useState<JobEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [restartOpen, setRestartOpen] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [showOps, setShowOps] = useState(false)

  useEffect(() => {
    const previous = document.title
    if (notFound) {
      document.title = t.notFoundHeading
    } else {
      const label = job ? jobDocumentLabel(job) : jobId
      document.title = t.jobDocumentTitle(label)
    }
    return () => {
      document.title = previous
    }
  }, [jobId, job, notFound])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      setNotFound(false)
      try {
        const [nextJob, nextHistory] = await Promise.all([
          client.getJob(jobId),
          client.getJobHistory(jobId, { audience: 'all' }),
        ])
        if (cancelled) {
          return
        }
        const nextChildren = await resolveChildren(nextJob)
        if (cancelled) {
          return
        }
        setJob(nextJob)
        setHistory(nextHistory)
        setChildren(nextChildren)
      } catch (err: unknown) {
        if (cancelled) {
          return
        }
        if (isNotFoundError(err)) {
          setNotFound(true)
          setJob(null)
          setHistory([])
          setChildren([])
        } else {
          setError(explainCaughtError(err, t.errorJob))
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    return events.subscribe(
      jobId,
      (event) => {
        setHistory((prev) => {
          const key = eventKey(event)
          if (prev.some((item) => eventKey(item) === key)) {
            return prev
          }
          return [...prev, event]
        })
        if (isLifecycleJobEvent(event)) {
          void client
            .getJob(jobId)
            .then(async (next) => {
              setJob(next)
              setChildren(await loadChildren(next, event.stage === 'child'))
            })
            .catch(() => undefined)
        }
      },
      'history',
    )
  }, [jobId])

  const active =
    (job != null && isJobActive(job.status)) ||
    children.some((child) => child.status != null && isJobActive(child.status))
  const cancellable = job != null && isJobCancellable(job.status)
  const restartable = job != null && job.status === 'cancelled'

  async function confirmRestart(mode: RestartMode) {
    if (!job || restarting) {
      return
    }
    setRestarting(true)
    setRestartOpen(false)
    setError(null)
    try {
      const restartOptions = mode === 'remaining' ? { mode } : {}
      const created =
        job.type === 'upload'
          ? await withGooglePhotosAccessToken((accessToken) =>
              client.restartJob(job.id, { accessToken, ...restartOptions }),
            )
          : await client.restartJob(job.id, restartOptions)
      announceRunSubmitted(created.id, created.number)
      trackRun({
        id: created.id,
        kind: kindFromJobType(created.type),
        status: created.status,
        error: created.error,
        number: created.number,
      })
      navigate(`/jobs/${created.id}`)
    } catch (err: unknown) {
      if (err instanceof GoogleAuthCancelledError) {
        return
      }
      setError(explainCaughtError(err, t.errorRestart))
    } finally {
      setRestarting(false)
    }
  }

  async function confirmCancel() {
    if (!job || cancelling) {
      return
    }
    setCancelling(true)
    setCancelOpen(false)
    setError(null)
    try {
      const next = await client.cancelJob(job.id)
      setJob(next)
      setChildren(await resolveChildren(next))
      setHistory(await client.getJobHistory(next.id, { audience: 'all' }))
    } catch (err: unknown) {
      setError(explainCaughtError(err, t.errorCancel))
      try {
        const next = await client.getJob(job.id)
        setJob(next)
        setChildren(await resolveChildren(next))
      } catch {
        // keep cancel error
      }
    } finally {
      setCancelling(false)
    }
  }

  useEffect(() => {
    if (!active) {
      return
    }
    const intervalId = window.setInterval(() => {
      void client
        .getJob(jobId)
        .then(async (next) => {
          setJob(next)
          setChildren(await loadChildren(next, true))
        })
        .catch(() => undefined)
    }, POLL_MS)
    return () => window.clearInterval(intervalId)
  }, [jobId, active])

  const scrapeUrl = job ? jobScrapeUrl(job) : null
  const galleryTitle = job ? jobGalleryTitle(job) : null
  const folderLabel = job ? jobFolderLabel(job) : null
  const headers = job ? headerItems(job) : []
  const albumHref = job ? albumDeskHref(job, children) : null
  const photoCount = job ? jobPhotoCount(job) : null
  const photosUrl = job ? jobPhotosUrl(job) : null

  if (notFound) {
    return <NotFoundPage />
  }

  return (
    <section className="job-detail">
      <div className="job-detail__stage">
        <h2 className="job-detail__heading">{t.jobDetailHeading}</h2>
        {error ? (
          <p className="job-detail__alert" role="alert" dir="auto">
            {error}
          </p>
        ) : null}
        {loading && !job ? <LoadingSpinner label={t.loadingJob} /> : null}
        {job ? (
          <dl className="job-detail__fields">
            {job.number != null ? (
              <Field label={t.jobNumberLabel}>
                <span className="job-detail__number" dir="ltr">
                  {job.number}
                </span>
              </Field>
            ) : null}
            <Field label={t.jobIdLabel}>
              <code className="job-detail__id" dir="ltr">
                {job.id}
              </code>
            </Field>
            <Field label={t.jobTypeHeading}>
              <span className="job-detail__type-label">{jobTypeLabel(job.type)}</span>
            </Field>
            {job.auto_publish ? (
              <Field label={t.jobAutoPublishLabel}>
                <span>{t.autoPublishLabel}</span>
              </Field>
            ) : null}
            <Field label={t.jobStatusHeading}>
              <span className="job-detail__status-row">
                <JobStatusBadge status={job.status} />
                {cancellable ? (
                  <button
                    type="button"
                    className="job-detail__cancel"
                    disabled={cancelling}
                    onClick={() => setCancelOpen(true)}
                  >
                    {cancelling ? t.cancelling : t.cancelJob}
                  </button>
                ) : null}
                {restartable ? (
                  <button
                    type="button"
                    className="job-detail__restart"
                    disabled={restarting}
                    onClick={() => setRestartOpen(true)}
                  >
                    {restarting ? t.restarting : t.restartJob}
                  </button>
                ) : null}
              </span>
            </Field>
            {job.type === 'scrape' ? (
              <>
                {scrapeUrl ? (
                  <Field label={t.jobUrlLabel}>
                    {/^https?:\/\//i.test(scrapeUrl) ? (
                      <a
                        className="job-detail__link"
                        href={scrapeUrl}
                        target="_blank"
                        rel="noreferrer"
                        dir="ltr"
                      >
                        {scrapeUrl}
                      </a>
                    ) : (
                      <span dir="ltr">{scrapeUrl}</span>
                    )}
                  </Field>
                ) : null}
                {job.parent_job_id ? (
                  <Field label={t.jobParentLabel}>
                    <Link className="job-detail__link" to={`/jobs/${job.parent_job_id}`} dir="ltr">
                      {job.parent_job_id}
                    </Link>
                  </Field>
                ) : null}
                {headers.length > 0 ? (
                  <Field label={t.jobHeadersLabel}>
                    <ul className="job-detail__headers">
                      {headers.map((header) => (
                        <li key={header.name} dir="ltr">
                          <code>{header.name}</code>
                          {header.value ? `: ${header.value}` : null}
                        </li>
                      ))}
                    </ul>
                  </Field>
                ) : null}
              </>
            ) : (
              <>
                {galleryTitle ? (
                  <Field label={t.titleLabel}>
                    <span dir="auto">{galleryTitle}</span>
                  </Field>
                ) : null}
                {folderLabel ? (
                  <Field label={t.jobFolderLabel}>
                    <span dir="auto">{folderLabel}</span>
                  </Field>
                ) : null}
                {job.source_job_id ? (
                  <Field label={t.jobSourceLabel}>
                    <Link className="job-detail__link" to={`/jobs/${job.source_job_id}`} dir="ltr">
                      {job.source_job_id}
                    </Link>
                  </Field>
                ) : null}
                {photoCount != null ? (
                  <Field label={t.photosHeading}>
                    <span dir="ltr">{t.historyPhotoCount(photoCount)}</span>
                  </Field>
                ) : null}
              </>
            )}
            <Field label={t.jobCreatedLabel}>{formatJobDate(job.created_at)}</Field>
            {job.updated_at ? (
              <Field label={t.jobUpdatedLabel}>{formatJobDate(job.updated_at)}</Field>
            ) : null}
            {job.finished_at ? (
              <Field label={t.jobFinishedLabel}>{formatJobDate(job.finished_at)}</Field>
            ) : null}
            {job.error || job.error_code ? (
              <Field label={t.jobErrorHeading}>
                <span className="job-detail__error" dir="auto">
                  {jobErrorMessage(job) || job.error}
                </span>
              </Field>
            ) : null}
            {job.warnings && job.warnings.length > 0 ? (
              <Field label={t.jobWarningsHeading}>
                <ul className="job-detail__warnings">
                  {job.warnings.map((warning) => (
                    <li key={warning} dir="auto">
                      {warning}
                    </li>
                  ))}
                </ul>
              </Field>
            ) : null}
            {photosUrl ? (
              <Field label={t.openPhotosAlbum}>
                <a
                  className="job-detail__link"
                  href={photosUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t.openPhotosAlbum}
                </a>
              </Field>
            ) : null}
            {albumHref ? (
              <Field label={t.openAlbum}>
                <Link className="job-detail__link" to={albumHref}>
                  {t.openAlbum}
                </Link>
              </Field>
            ) : null}
          </dl>
        ) : null}
      </div>

      {children.length > 0 ? (
        <div className="job-detail__stage">
          <h2 className="job-detail__heading">{t.jobChildrenHeading}</h2>
          <ul className="job-detail__children">
            {children.map((child) => {
              const label = childDisplayLabel(child)
              return (
                <li key={child.id} className="job-detail__child">
                  {child.number != null ? (
                    <span className="job-detail__child-number" dir="ltr">
                      {child.number}
                    </span>
                  ) : null}
                  <Link
                    className="job-detail__link job-detail__child-id"
                    to={`/jobs/${child.id}`}
                    dir="ltr"
                    aria-label={t.jobsOpenAria(label)}
                  >
                    {child.id}
                  </Link>
                  {child.type ? (
                    <span className="job-detail__type-label">{jobTypeLabel(child.type)}</span>
                  ) : null}
                  {child.status ? <JobStatusBadge status={child.status} /> : null}
                  {label !== child.id ? (
                    <span className="job-detail__child-title" dir="auto">
                      {label}
                    </span>
                  ) : null}
                  {childHasAlbumDesk(child) ? (
                    <Link className="job-detail__link" to={`/albums/${child.id}`}>
                      {t.openAlbum}
                    </Link>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}

      <div className="job-detail__stage">
        <div className="job-detail__log-header">
          <h2 className="job-detail__heading">{t.runHistoryHeading}</h2>
          <label className="job-detail__tech-toggle">
            <input
              type="checkbox"
              checked={showOps}
              onChange={(event) => setShowOps(event.target.checked)}
            />
            {t.technicalLogs}
          </label>
        </div>
        {history.length === 0 && !loading ? (
          <p className="job-detail__empty">{t.runHistoryEmpty}</p>
        ) : null}
        {history.length > 0 ? (
          <ol className="job-detail__log" aria-label={t.runHistoryHeading}>
            {history
              .filter((item) => shouldShowJobLog(item, showOps))
              .map((event, index) => {
                const tone = jobLogTone(event)
                const progress = event.total > 0 ? `${event.current}/${event.total}` : ''
                const etaSeconds = eventEtaSeconds(event)
                const locale = APP_LANGUAGE === 'he' ? 'he-IL' : 'en-US'
                return (
                  <li
                    key={`${eventKey(event)}-${index}`}
                    className={[
                      'job-detail__log-line',
                      tone ? `job-detail__log-line--${tone}` : '',
                      event.audience === 'ops' ? 'job-detail__log-line--ops' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    <time
                      className="job-detail__log-time"
                      dateTime={event.occurred_at ?? undefined}
                      dir="ltr"
                    >
                      {formatLogTime(event.occurred_at, locale)}
                    </time>
                    <span className="job-detail__log-progress" dir="ltr">
                      {progress}
                    </span>
                    <span className="job-detail__log-message" dir="auto">
                      {jobLogMessage(event, t.jobLogLifecycle)}
                    </span>
                    {etaSeconds != null ? (
                      <span className="job-detail__eta" dir="ltr">
                        {t.etaLeft(etaSeconds)}
                      </span>
                    ) : null}
                  </li>
                )
              })}
          </ol>
        ) : null}
      </div>
      <CancelJobDialog
        open={cancelOpen}
        jobId={job?.id ?? null}
        onCancel={() => setCancelOpen(false)}
        onConfirm={() => void confirmCancel()}
      />
      <RestartJobDialog
        open={restartOpen}
        jobId={job?.id ?? null}
        onCancel={() => setRestartOpen(false)}
        onConfirm={(mode) => void confirmRestart(mode)}
      />
    </section>
  )
}
