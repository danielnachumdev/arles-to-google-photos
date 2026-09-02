import type { JobSummary } from '../api/types.ts'
import { jobStatusLabel, jobTypeLabel } from './language.ts'

export function matchesJobSearch(job: JobSummary, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) {
    return true
  }
  const scrape = job.type === 'scrape'
  const fields = [
    scrape ? null : job.title,
    scrape ? null : job.folder_label,
    job.scrape_url,
    job.id,
    job.status,
    job.type,
    job.number != null ? String(job.number) : null,
    jobStatusLabel(job.status),
    jobTypeLabel(job.type),
  ]
  return fields.some((field) => (field ?? '').toLowerCase().includes(needle))
}

export function filterJobs(jobs: JobSummary[], query: string): JobSummary[] {
  return jobs.filter((job) => matchesJobSearch(job, query))
}
