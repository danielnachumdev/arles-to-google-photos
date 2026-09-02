import type { JobStatus } from '../api/types.ts'
import { t } from './language.ts'
import { toast } from './toast.ts'

export type TrackedRunKind = 'preview' | 'upload' | 'scrape'

export type TrackedRun = {
  id: string
  kind: TrackedRunKind
  status?: JobStatus
  error?: string | null
  error_code?: string | null
  scrape_url?: string | null
  number?: number | null
}

export type ListedRunSnapshot = {
  id: string
  status: JobStatus
  type?: string | null
  error?: string | null
  error_code?: string | null
  scrape_url?: string | null
  number?: number | null
}

const SUBMIT_TOAST_MS = 8000

const listeners = new Set<() => void>()
const submittedKeys = new Set<string>()
const completedKeys = new Set<string>()
const generationById = new Map<string, number>()

let runs: TrackedRun[] = []

function emit(): void {
  listeners.forEach((listener) => listener())
}

function runKey(id: string, gen?: number): string {
  return `${id}:${gen ?? generationById.get(id) ?? 0}`
}

export function isTerminalJobStatus(
  status: string | undefined,
): status is 'done' | 'failed' | 'cancelled' {
  return status === 'done' || status === 'failed' || status === 'cancelled'
}

export function subscribeTrackedRuns(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  return () => {
    listeners.delete(onStoreChange)
  }
}

export function getTrackedRuns(): TrackedRun[] {
  return runs
}

export function kindFromJobType(jobType: string | null | undefined): TrackedRunKind {
  if (jobType === 'upload') {
    return 'upload'
  }
  if (jobType === 'scrape') {
    return 'scrape'
  }
  return 'preview'
}

export function runHref(jobId: string): string {
  return `/jobs/${jobId}`
}

export function jobToastLabel(id: string, number?: number | null): string {
  if (typeof number === 'number' && Number.isFinite(number)) {
    return `#${number}`
  }
  return id
}

export function announceRunSubmitted(jobId: string, number?: number | null): void {
  let gen = generationById.get(jobId) ?? 0
  if (gen > 0 && completedKeys.has(runKey(jobId, gen))) {
    gen += 1
    generationById.set(jobId, gen)
  } else if (gen === 0) {
    gen = 1
    generationById.set(jobId, gen)
  }
  const key = runKey(jobId, gen)
  if (submittedKeys.has(key)) {
    return
  }
  submittedKeys.add(key)
  toast.regular({
    message: t.toastRunSubmitted(jobToastLabel(jobId, number)),
    href: runHref(jobId),
    linkLabel: t.toastOpenRun,
    durationMs: SUBMIT_TOAST_MS,
  })
}

export function trackRun(run: TrackedRun): void {
  if (!generationById.has(run.id)) {
    generationById.set(run.id, 1)
  }
  const existing = runs.find((item) => item.id === run.id)
  if (existing) {
    if (
      existing.kind === run.kind &&
      existing.status === run.status &&
      existing.error === run.error &&
      existing.error_code === run.error_code &&
      existing.scrape_url === run.scrape_url &&
      existing.number === run.number
    ) {
      return
    }
    runs = runs.map((item) => (item.id === run.id ? { ...item, ...run } : item))
    emit()
    return
  }
  runs = [...runs, run]
  emit()
}

export function untrackRun(id: string): void {
  const next = runs.filter((item) => item.id !== id)
  if (next.length === runs.length) {
    return
  }
  runs = next
  emit()
}

export function consumeRunToast(id: string): boolean {
  const gen = generationById.get(id) ?? 1
  const key = runKey(id, gen)
  if (completedKeys.has(key)) {
    return false
  }
  completedKeys.add(key)
  return true
}

export function diffListedJobs(
  known: ReadonlyMap<string, JobStatus>,
  listed: ListedRunSnapshot[],
): {
  created: ListedRunSnapshot[]
  transitioned: Array<{ job: ListedRunSnapshot; from: JobStatus }>
} {
  const created: ListedRunSnapshot[] = []
  const transitioned: Array<{ job: ListedRunSnapshot; from: JobStatus }> = []
  for (const job of listed) {
    const prev = known.get(job.id)
    if (prev === undefined) {
      created.push(job)
      continue
    }
    if (prev !== job.status) {
      transitioned.push({ job, from: prev })
    }
  }
  return { created, transitioned }
}

export function rememberListedJobs(
  known: Map<string, JobStatus>,
  listed: ListedRunSnapshot[],
): void {
  for (const job of listed) {
    known.set(job.id, job.status)
  }
}

export function clearTrackedRuns(): void {
  submittedKeys.clear()
  completedKeys.clear()
  generationById.clear()
  if (runs.length === 0) {
    return
  }
  runs = []
  emit()
}
