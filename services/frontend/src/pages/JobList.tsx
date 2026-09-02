import { useCallback, useEffect, useId, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import { JobEventSource } from '../api/events.ts'
import type { JobSummary, OrchestratorSettings, RestartMode } from '../api/types.ts'
import { CancelJobDialog } from '../components/CancelJobDialog.tsx'
import { ConfirmDialog } from '../components/ConfirmDialog.tsx'
import { RestartJobDialog } from '../components/RestartJobDialog.tsx'
import { JobStatusBadge } from '../components/JobStatusBadge.tsx'
import { LoadingSpinner } from '../components/LoadingSpinner.tsx'
import { GoogleAuthCancelledError } from '../lib/googleAuth.ts'
import { withGooglePhotosAccessToken } from '../lib/withGooglePhotosToken.ts'
import { formatJobDate } from '../lib/formatJobDate.ts'
import { explainCaughtError } from '../lib/formatApiError.ts'
import {
  formatJobDuration,
  isJobActive,
  isJobArchivable,
  isJobCancellable,
  isJobProcessing,
  jobDurationSeconds,
} from '../lib/formatJobDuration.ts'
import { jobErrorMessage } from '../lib/jobFields.ts'
import { filterJobs } from '../lib/jobSearch.ts'
import { jobTypeLabel, t } from '../lib/language.ts'
import {
  announceRunSubmitted,
  getTrackedRuns,
  isTerminalJobStatus,
  kindFromJobType,
  subscribeTrackedRuns,
  trackRun,
} from '../lib/runTracker.ts'
import './JobList.css'

const client = new MigrationClient()
const events = new JobEventSource()
export const JOB_LIST_POLL_MS = 2500
export const JOB_LIST_SCRAPE_POLL_MS = 750
const TICK_MS = 1000

function activeScrapeIdsFromList(jobs: JobSummary[]): string[] {
  return jobs
    .filter((job) => job.type === 'scrape' && isJobActive(job.status))
    .map((job) => job.id)
}

export function JobList() {
  const searchId = useId()
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [cancelTarget, setCancelTarget] = useState<JobSummary | null>(null)
  const [cancellingId, setCancellingId] = useState<string | null>(null)
  const [restartTarget, setRestartTarget] = useState<JobSummary | null>(null)
  const [restartingId, setRestartingId] = useState<string | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<JobSummary | null>(null)
  const [archivingId, setArchivingId] = useState<string | null>(null)
  const [queue, setQueue] = useState<OrchestratorSettings | null>(null)
  const trackedRuns = useSyncExternalStore(subscribeTrackedRuns, getTrackedRuns, getTrackedRuns)
  const trackedScrapeIds = trackedRuns
    .filter((run) => run.kind === 'scrape' && !isTerminalJobStatus(run.status))
    .map((run) => run.id)
  const hasTrackedScrape = trackedScrapeIds.length > 0
  const listedScrapeIds = activeScrapeIdsFromList(jobs)
  const scrapeWatchKey = Array.from(new Set([...trackedScrapeIds, ...listedScrapeIds]))
    .sort()
    .join('\0')

  const refreshJobs = useCallback(async () => {
    try {
      const [next, settings] = await Promise.all([
        client.listJobs(),
        client.getSettings().catch(() => null),
      ])
      setJobs(next)
      if (settings) {
        setQueue(settings)
      }
      setError(null)
    } catch (err: unknown) {
      setError(explainCaughtError(err, t.errorJob))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void Promise.all([client.listJobs(), client.getSettings().catch(() => null)])
      .then(([next, settings]) => {
        if (cancelled) {
          return
        }
        setJobs(next)
        if (settings) {
          setQueue(settings)
        }
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return
        }
        setError(explainCaughtError(err, t.errorJob))
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const anyActive = jobs.some((job) => isJobActive(job.status))
  const anyRunning = jobs.some((job) => isJobProcessing(job.status))
  const anyActiveScrape = listedScrapeIds.length > 0 || hasTrackedScrape
  const shouldPoll = anyActive || hasTrackedScrape
  const pollMs = anyActiveScrape ? JOB_LIST_SCRAPE_POLL_MS : JOB_LIST_POLL_MS

  useEffect(() => {
    if (!shouldPoll) {
      return
    }
    const intervalId = window.setInterval(() => {
      void refreshJobs()
    }, pollMs)
    return () => window.clearInterval(intervalId)
  }, [shouldPoll, pollMs, refreshJobs])

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === 'hidden') {
        return
      }
      void refreshJobs()
    }
    window.addEventListener('focus', onVisible)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('focus', onVisible)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refreshJobs])

  useEffect(() => {
    if (!scrapeWatchKey) {
      return
    }
    const unsubscribes = scrapeWatchKey.split('\0').map((jobId) =>
      events.subscribe(
        jobId,
        (event) => {
          if (event.stage === 'child' || event.stage === 'waiting') {
            void refreshJobs()
          }
        },
        'scrape',
      ),
    )
    return () => {
      unsubscribes.forEach((unsubscribe) => unsubscribe())
    }
  }, [scrapeWatchKey, refreshJobs])

  useEffect(() => {
    if (!anyRunning) {
      return
    }
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now())
    }, TICK_MS)
    return () => window.clearInterval(intervalId)
  }, [anyRunning])

  const visible = filterJobs(jobs, query)

  async function confirmRestart(mode: RestartMode) {
    const target = restartTarget
    if (!target || restartingId) {
      return
    }
    setRestartTarget(null)
    setRestartingId(target.id)
    setError(null)
    try {
      const restartOptions = mode === 'remaining' ? { mode } : {}
      const created =
        target.type === 'upload'
          ? await withGooglePhotosAccessToken((accessToken) =>
              client.restartJob(target.id, { accessToken, ...restartOptions }),
            )
          : await client.restartJob(target.id, restartOptions)
      announceRunSubmitted(created.id, created.number)
      trackRun({
        id: created.id,
        kind: kindFromJobType(created.type),
        status: created.status,
        error: created.error,
        number: created.number,
      })
      const listed = await client.listJobs()
      setJobs(listed)
    } catch (err: unknown) {
      if (err instanceof GoogleAuthCancelledError) {
        return
      }
      setError(explainCaughtError(err, t.errorRestart))
    } finally {
      setRestartingId(null)
    }
  }

  async function confirmArchive() {
    const target = archiveTarget
    if (!target || archivingId) {
      return
    }
    setArchiveTarget(null)
    setArchivingId(target.id)
    setError(null)
    try {
      const result = await client.archiveJob(target.id)
      const hidden = new Set(
        result.archived_ids.length > 0 ? result.archived_ids : [target.id],
      )
      setJobs((prev) => prev.filter((job) => !hidden.has(job.id)))
      const listed = await client.listJobs()
      setJobs(listed)
    } catch (err: unknown) {
      setError(explainCaughtError(err, t.errorArchive))
      try {
        const listed = await client.listJobs()
        setJobs(listed)
      } catch {
        // keep archive error
      }
    } finally {
      setArchivingId(null)
    }
  }

  async function confirmCancel() {
    const target = cancelTarget
    if (!target || cancellingId) {
      return
    }
    setCancelTarget(null)
    setCancellingId(target.id)
    setError(null)
    try {
      const updated = await client.cancelJob(target.id)
      setJobs((prev) =>
        prev.map((job) =>
          job.id === updated.id
            ? {
                ...job,
                status: updated.status,
                error: updated.error,
              }
            : job,
        ),
      )
      const listed = await client.listJobs()
      setJobs(listed)
    } catch (err: unknown) {
      setError(explainCaughtError(err, t.errorCancel))
      try {
        const listed = await client.listJobs()
        setJobs(listed)
      } catch {
        // keep cancel error
      }
    } finally {
      setCancellingId(null)
    }
  }

  return (
    <section className="job-list">
      <div className="job-list__stage">
        <h2 className="job-list__heading">{t.jobsHeading}</h2>
        <p className="job-list__lede">{t.jobsLede}</p>
        {queue ? (
          <p className="job-list__queue" dir="ltr">
            {t.jobsQueueSummary(
              queue.running,
              queue.pending,
              queue.waiting ?? 0,
              queue.max_concurrent_jobs,
            )}
          </p>
        ) : null}
        <label className="job-list__search-label" htmlFor={searchId}>
          {t.jobsSearchLabel}
          <input
            id={searchId}
            className="job-list__search"
            type="search"
            value={query}
            placeholder={t.jobsSearchPlaceholder}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        {error ? (
          <p className="job-list__error" role="alert" dir="auto">
            {error}
          </p>
        ) : null}
        {loading ? <LoadingSpinner label={t.loadingJobs} /> : null}
        {!loading && jobs.length === 0 && !error ? (
          <p className="job-list__empty">{t.jobsEmpty}</p>
        ) : null}
        {!loading && jobs.length > 0 && visible.length === 0 ? (
          <p className="job-list__empty">{t.jobsNoMatches}</p>
        ) : null}
        {!loading && visible.length > 0 ? (
          <div className="job-list__table-wrap">
            <table className="job-list__table">
              <thead>
                <tr>
                  <th scope="col">{t.jobsColNumber}</th>
                  <th scope="col">{t.jobsColId}</th>
                  <th scope="col">{t.jobsColType}</th>
                  <th scope="col">{t.jobsColStatus}</th>
                  <th scope="col">{t.jobsColStart}</th>
                  <th scope="col">{t.jobsColEnd}</th>
                  <th scope="col">{t.jobsColDuration}</th>
                  <th scope="col">{t.jobsColError}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => {
                  const duration = formatJobDuration(jobDurationSeconds(item, nowMs))
                  return (
                    <tr key={item.id}>
                      <td className="job-list__number" dir="ltr">
                        {item.number != null ? item.number : t.missingValue}
                      </td>
                      <td>
                        <Link
                          to={`/jobs/${item.id}`}
                          className="job-list__id-link"
                          dir="ltr"
                          aria-label={t.jobsOpenAria(item.id)}
                        >
                          {item.id}
                        </Link>
                      </td>
                      <td>
                        <span className="job-list__type-label">{jobTypeLabel(item.type)}</span>
                      </td>
                      <td>
                        <span className="job-list__status-cell">
                          <JobStatusBadge status={item.status} />
                          {isJobCancellable(item.status) ? (
                            <button
                              type="button"
                              className="job-list__cancel"
                              disabled={cancellingId === item.id}
                              onClick={() => setCancelTarget(item)}
                            >
                              {cancellingId === item.id ? t.cancelling : t.cancelJob}
                            </button>
                          ) : null}
                          {item.status === 'cancelled' ? (
                            <button
                              type="button"
                              className="job-list__restart"
                              disabled={restartingId === item.id}
                              onClick={() => setRestartTarget(item)}
                            >
                              {restartingId === item.id ? t.restarting : t.restartJob}
                            </button>
                          ) : null}
                          {isJobArchivable(item.status) ? (
                            <button
                              type="button"
                              className="job-list__archive"
                              disabled={archivingId === item.id}
                              onClick={() => setArchiveTarget(item)}
                            >
                              {archivingId === item.id ? t.archiving : t.archiveJob}
                            </button>
                          ) : null}
                        </span>
                      </td>
                      <td className="job-list__start">{formatJobDate(item.created_at)}</td>
                      <td className="job-list__end">
                        {item.finished_at ? (
                          formatJobDate(item.finished_at)
                        ) : (
                          <span className="job-list__muted">{t.missingValue}</span>
                        )}
                      </td>
                      <td className="job-list__duration" dir="ltr">
                        {duration}
                      </td>
                      <td>
                        {item.status === 'failed' && (item.error || item.error_code) ? (
                          <span className="job-list__error-line" dir="auto">
                            {jobErrorMessage(item) || item.error}
                          </span>
                        ) : item.warnings && item.warnings.length > 0 ? (
                          <span
                            className="job-list__warning-line"
                            dir="auto"
                            title={item.warnings.join('\n')}
                          >
                            {item.warnings[0]}
                          </span>
                        ) : (
                          <span className="job-list__muted">{t.missingValue}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
      <CancelJobDialog
        open={cancelTarget !== null}
        jobId={cancelTarget?.id ?? null}
        onCancel={() => setCancelTarget(null)}
        onConfirm={() => void confirmCancel()}
      />
      <RestartJobDialog
        open={restartTarget !== null}
        jobId={restartTarget?.id ?? null}
        onCancel={() => setRestartTarget(null)}
        onConfirm={(mode) => void confirmRestart(mode)}
      />
      <ConfirmDialog
        open={archiveTarget !== null}
        title={t.confirmArchiveJobTitle}
        message={t.confirmArchiveJobBody}
        cancelLabel={t.confirmCancel}
        confirmLabel={t.confirmArchiveJobYes}
        onCancel={() => setArchiveTarget(null)}
        onConfirm={() => void confirmArchive()}
      />
    </section>
  )
}
