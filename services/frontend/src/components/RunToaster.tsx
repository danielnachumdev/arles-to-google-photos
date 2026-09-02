import { useEffect, useRef, useSyncExternalStore } from 'react'
import { MigrationClient } from '../api/client.ts'
import { JobEventSource } from '../api/events.ts'
import type { Job, JobEvent, JobStatus, JobSummary } from '../api/types.ts'
import { jobErrorMessage } from '../lib/jobFields.ts'
import { t } from '../lib/language.ts'
import {
  announceRunSubmitted,
  consumeRunToast,
  diffListedJobs,
  getTrackedRuns,
  isTerminalJobStatus,
  jobToastLabel,
  kindFromJobType,
  rememberListedJobs,
  runHref,
  subscribeTrackedRuns,
  trackRun,
  untrackRun,
  type ListedRunSnapshot,
  type TrackedRun,
} from '../lib/runTracker.ts'
import { toast } from '../lib/toast.ts'

const client = new MigrationClient()
const events = new JobEventSource()
export const RUN_WATCH_POLL_MS = 2500

function doneMessage(kind: TrackedRun['kind'], jobLabel: string): string {
  if (kind === 'upload') {
    return t.toastUploadDone(jobLabel)
  }
  if (kind === 'scrape') {
    return t.toastScrapeDone(jobLabel)
  }
  return t.toastPreviewDone(jobLabel)
}

function failedMessage(
  kind: TrackedRun['kind'],
  jobLabel: string,
  job: {
    type?: string | null
    error?: string | null
    error_code?: string | null
    scrape_url?: string | null
    url?: string | null
  },
): string {
  if (kind === 'upload') {
    return t.toastUploadFailed(jobLabel, (job.error ?? '').trim())
  }
  if (kind === 'scrape') {
    return t.toastScrapeFailed(jobLabel, jobErrorMessage({ ...job, type: 'scrape' }))
  }
  return t.toastPreviewFailed(jobLabel, (job.error ?? '').trim())
}

function isTerminalStage(stage: string): boolean {
  return (
    stage === 'preview_ready' ||
    stage === 'done' ||
    stage === 'error' ||
    stage === 'failed' ||
    stage === 'cancelled'
  )
}

function asListedRun(job: JobSummary): ListedRunSnapshot {
  return {
    id: job.id,
    status: job.status,
    type: job.type,
    error: job.error,
    error_code: job.error_code,
    scrape_url: job.scrape_url,
    product_url: job.product_url,
    number: job.number,
  }
}

function completionActions(jobId: string, productUrl?: string | null): {
  href: string
  linkLabel: string
  actions?: Array<{ href: string; label: string; external?: boolean }>
  durationMs?: number
} {
  const href = runHref(jobId)
  const linkLabel = t.toastOpenRun
  const albumUrl = (productUrl ?? '').trim()
  if (!albumUrl) {
    return { href, linkLabel }
  }
  return {
    href,
    linkLabel,
    durationMs: 8000,
    actions: [
      { href: albumUrl, label: t.toastOpenAlbum, external: true },
      { href, label: linkLabel },
    ],
  }
}

function toastCompletion(job: {
  id: string
  kind: TrackedRun['kind']
  status: 'done' | 'failed' | 'cancelled'
  error?: string | null
  error_code?: string | null
  scrape_url?: string | null
  product_url?: string | null
  number?: number | null
}): void {
  if (!consumeRunToast(job.id)) {
    untrackRun(job.id)
    return
  }
  const links = completionActions(
    job.id,
    job.status === 'done' ? job.product_url : null,
  )
  const jobLabel = jobToastLabel(job.id, job.number)
  if (job.status === 'done') {
    toast.good({
      message: doneMessage(job.kind, jobLabel),
      ...links,
    })
  } else if (job.status === 'cancelled') {
    toast.regular({
      message: t.toastRunCancelledJob(jobLabel),
      href: links.href,
      linkLabel: links.linkLabel,
    })
  } else {
    toast.bad({
      message: failedMessage(job.kind, jobLabel, job),
      href: links.href,
      linkLabel: links.linkLabel,
    })
  }
  untrackRun(job.id)
}

function followListedJob(job: ListedRunSnapshot): void {
  announceRunSubmitted(job.id, job.number)
  trackRun({
    id: job.id,
    kind: kindFromJobType(job.type),
    status: job.status,
    error: job.error,
    error_code: job.error_code,
    scrape_url: job.scrape_url,
    product_url: job.product_url,
    number: job.number,
  })
}

function startWatch(run: TrackedRun): () => void {
  let cancelled = false
  let unsubscribeEvents: (() => void) | undefined
  let pollId: number | undefined

  function finish(job: {
    id: string
    kind: TrackedRun['kind']
    status: string
    error?: string | null
    error_code?: string | null
    scrape_url?: string | null
    product_url?: string | null
    number?: number | null
  }): void {
    if (cancelled || !isTerminalJobStatus(job.status)) {
      return
    }
    toastCompletion({
      id: job.id,
      kind: job.kind,
      status: job.status,
      error: job.error,
      error_code: job.error_code,
      scrape_url: job.scrape_url,
      product_url: job.product_url,
      number: job.number,
    })
  }

  async function refresh(): Promise<void> {
    if (cancelled) {
      return
    }
    try {
      const job = await client.getJob(run.id)
      finish({
        id: job.id,
        kind: kindFromJobType(job.type) || run.kind,
        status: job.status,
        error: job.error,
        error_code: job.error_code ?? run.error_code,
        scrape_url: job.scrape_url ?? run.scrape_url,
        product_url: job.product_url ?? run.product_url,
        number: job.number ?? run.number,
      })
    } catch {
      return
    }
  }

  function onEvent(event: JobEvent): void {
    if (cancelled || !isTerminalStage(event.stage)) {
      return
    }
    const cancelledStage = event.stage === 'cancelled'
    const failed = event.stage === 'error' || event.stage === 'failed'
    void client
      .getJob(run.id)
      .then((job: Job) => {
        if (cancelled) {
          return
        }
        if (isTerminalJobStatus(job.status)) {
          finish({
            id: job.id,
            kind: kindFromJobType(job.type) || run.kind,
            status: job.status,
            error: job.error,
            error_code: job.error_code ?? run.error_code,
            scrape_url: job.scrape_url ?? run.scrape_url,
            product_url: job.product_url ?? run.product_url,
            number: job.number ?? run.number,
          })
          return
        }
        finish({
          id: run.id,
          kind: kindFromJobType(job.type) || run.kind,
          status: cancelledStage ? 'cancelled' : failed ? 'failed' : 'done',
          error: failed ? job.error || event.message || null : null,
          error_code: failed ? job.error_code ?? run.error_code : null,
          scrape_url: job.scrape_url ?? run.scrape_url,
          product_url: job.product_url ?? run.product_url,
          number: job.number ?? run.number,
        })
      })
      .catch(() => {
        finish({
          id: run.id,
          kind: run.kind,
          status: cancelledStage ? 'cancelled' : failed ? 'failed' : 'done',
          error: failed ? event.message || null : null,
          error_code: failed ? run.error_code : null,
          scrape_url: run.scrape_url,
          product_url: run.product_url,
          number: run.number,
        })
      })
  }

  if (isTerminalJobStatus(run.status)) {
    toastCompletion({
      id: run.id,
      kind: run.kind,
      status: run.status,
      error: run.error,
      error_code: run.error_code,
      scrape_url: run.scrape_url,
      product_url: run.product_url,
      number: run.number,
    })
    return () => {
      cancelled = true
    }
  }

  unsubscribeEvents = events.subscribe(run.id, onEvent, run.kind === 'upload' ? 'publish' : 'ingest')
  pollId = window.setInterval(() => {
    void refresh()
  }, RUN_WATCH_POLL_MS)
  void refresh()

  return () => {
    cancelled = true
    unsubscribeEvents?.()
    if (pollId !== undefined) {
      window.clearInterval(pollId)
    }
  }
}

export function RunToaster() {
  const runs = useSyncExternalStore(subscribeTrackedRuns, getTrackedRuns, getTrackedRuns)
  const watchers = useRef(new Map<string, () => void>())
  const knownStatuses = useRef(new Map<string, JobStatus>())
  const snapshotted = useRef(false)

  useEffect(() => {
    const active = new Set(runs.map((run) => run.id))
    for (const run of runs) {
      if (!watchers.current.has(run.id)) {
        watchers.current.set(run.id, startWatch(run))
      }
    }
    for (const [id, stop] of [...watchers.current]) {
      if (!active.has(id)) {
        stop()
        watchers.current.delete(id)
      }
    }
  }, [runs])

  useEffect(() => {
    let cancelled = false
    let pollId: number | undefined

    async function refreshList(): Promise<void> {
      if (cancelled) {
        return
      }
      try {
        const jobs = await client.listJobs()
        if (cancelled) {
          return
        }
        const listed = jobs.map(asListedRun)
        if (!snapshotted.current) {
          rememberListedJobs(knownStatuses.current, listed)
          snapshotted.current = true
          return
        }
        const { created, transitioned } = diffListedJobs(knownStatuses.current, listed)
        rememberListedJobs(knownStatuses.current, listed)
        for (const job of created) {
          followListedJob(job)
        }
        for (const { job, from } of transitioned) {
          if (job.status === 'running' && isTerminalJobStatus(from)) {
            followListedJob(job)
            continue
          }
          if (isTerminalJobStatus(job.status) && !isTerminalJobStatus(from)) {
            trackRun({
              id: job.id,
              kind: kindFromJobType(job.type),
              status: job.status,
              error: job.error,
              error_code: job.error_code,
              scrape_url: job.scrape_url,
              product_url: job.product_url,
              number: job.number,
            })
          }
        }
      } catch {
        return
      }
    }

    void refreshList()
    pollId = window.setInterval(() => {
      void refreshList()
    }, RUN_WATCH_POLL_MS)

    return () => {
      cancelled = true
      if (pollId !== undefined) {
        window.clearInterval(pollId)
      }
      watchers.current.forEach((stop) => stop())
      watchers.current.clear()
    }
  }, [])

  return null
}
