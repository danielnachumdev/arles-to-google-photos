import type { JobSummary } from '../api/types.ts'
import { t } from './language.ts'

export function isJobProcessing(status: string): boolean {
  return status === 'running' || status === 'waiting'
}

export function isJobActive(status: string): boolean {
  return status === 'pending' || status === 'running' || status === 'waiting'
}

export function isJobCancellable(status: string): boolean {
  return status === 'pending' || status === 'running' || status === 'waiting'
}

export function isJobArchivable(status: string): boolean {
  return status === 'done' || status === 'failed' || status === 'cancelled'
}

export function formatJobDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return t.missingValue
  }
  const total = Math.floor(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

export function jobDurationSeconds(job: JobSummary, nowMs: number): number | null {
  if (job.status === 'pending') {
    return job.duration_seconds ?? null
  }
  if (job.status === 'running') {
    const startIso = job.running_started_at || job.started_at
    if (startIso) {
      const startMs = Date.parse(startIso)
      if (!Number.isNaN(startMs)) {
        const current = Math.max(0, Math.floor((nowMs - startMs) / 1000))
        const snapshot = job.duration_seconds
        if (snapshot != null && Number.isFinite(snapshot)) {
          return Math.max(snapshot, current)
        }
        return current
      }
    }
    return job.duration_seconds ?? null
  }
  if (job.duration_seconds != null) {
    return job.duration_seconds
  }
  const startMs = job.created_at ? Date.parse(job.created_at) : Number.NaN
  if (Number.isNaN(startMs)) {
    return null
  }
  const endIso = job.finished_at || job.updated_at
  if (endIso) {
    const endMs = Date.parse(endIso)
    if (!Number.isNaN(endMs)) {
      return Math.max(0, Math.floor((endMs - startMs) / 1000))
    }
  }
  return null
}
