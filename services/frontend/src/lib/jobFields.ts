import type { ImportOrigin, Job, JobChild, JobType } from '../api/types.ts'
import { t } from './language.ts'

export function isHostnameLabel(value: string | null | undefined): boolean {
  if (!value) {
    return false
  }
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/i.test(
    value.trim(),
  )
}

export function jobScrapeUrl(job: {
  url?: string | null
  scrape_url?: string | null
}): string | null {
  const value = job.scrape_url?.trim() || job.url?.trim() || ''
  return value || null
}

export function parseHttpStatus(error: string | null | undefined): string | null {
  const match = (error ?? '').match(/\bHTTP\s+(\d{3})\b/i)
  return match?.[1] ?? null
}

export function jobErrorMessage(job: {
  type?: JobType | string | null
  error?: string | null
  error_code?: string | null
  scrape_url?: string | null
  url?: string | null
}): string {
  const code = (job.error_code ?? '').trim()
  const url = jobScrapeUrl(job)
  if (code === 'not_arles' || code === 'unsupported_url') {
    return t.errorScrapeUnsupported(url)
  }
  if (code === 'fetch_failed') {
    return t.errorScrapeFetch(url, parseHttpStatus(job.error))
  }
  if (code === 'scrape_empty') {
    return t.errorScrapeEmpty(url)
  }
  const detail = (job.error ?? '').trim()
  if (code === 'interrupted' || detail === 'interrupted') {
    return t.errorInterrupted
  }
  if (job.type === 'scrape') {
    return detail ? t.errorScrape(detail) : t.errorScrape('')
  }
  return detail
}

export function inferImportOrigin(job: {
  import_origin?: ImportOrigin | string | null
  type?: JobType | null
  parent_job_id?: string | null
  scrape_url?: string | null
  url?: string | null
}): ImportOrigin {
  const explicit = job.import_origin?.trim()
  if (explicit === 'folder' || explicit === 'web') {
    return explicit
  }
  if (job.parent_job_id || job.type === 'scrape' || jobScrapeUrl(job)) {
    return 'web'
  }
  return 'folder'
}

export function isWebImportJob(job: {
  import_origin?: ImportOrigin | string | null
  type?: JobType | null
  parent_job_id?: string | null
  scrape_url?: string | null
  url?: string | null
}): boolean {
  return inferImportOrigin(job) === 'web'
}

export function jobGalleryTitle(job: {
  type?: JobType
  preview?: { title?: string | null } | null
  title?: string | null
}): string | null {
  if (job.type === 'scrape') {
    return null
  }
  const fromPreview = job.preview?.title?.trim() || ''
  if (fromPreview && !isHostnameLabel(fromPreview)) {
    return fromPreview
  }
  const fromTitle = job.title?.trim() || ''
  if (fromTitle && !isHostnameLabel(fromTitle)) {
    return fromTitle
  }
  return null
}

export function jobFolderLabel(job: {
  type?: JobType
  folder_label?: string | null
}): string | null {
  if (job.type === 'scrape') {
    return null
  }
  const label = job.folder_label?.trim() || ''
  if (!label || isHostnameLabel(label)) {
    return null
  }
  return label
}

export function jobDocumentLabel(job: Job): string {
  if (job.type === 'scrape') {
    return jobScrapeUrl(job) || job.id
  }
  return jobGalleryTitle(job) || jobFolderLabel(job) || job.id
}

export function childDisplayLabel(child: JobChild): string {
  if (child.type === 'scrape') {
    return jobScrapeUrl(child) || child.id
  }
  return jobGalleryTitle(child) || child.id
}

/** True when this run belongs on the album desk (/albums/:id), not only Jobs. */
export function jobHasAlbumDesk(job: {
  type?: string | null
  status?: string | null
  preview?: { title?: string | null } | null
  title?: string | null
}): boolean {
  if (job.preview?.title?.trim()) {
    return true
  }
  // Leaf ingest still running — preview arrives when parse finishes.
  if (
    job.type === 'preview' &&
    (job.status === 'pending' || job.status === 'running')
  ) {
    return true
  }
  return false
}

/**
 * Job id to open on the album desk. Hub/scrape parents without their own
 * preview use preview_job_id (first leaf child).
 */
export function albumDeskJobId(job: {
  id: string
  source_job_id?: string | null
  preview_job_id?: string | null
  preview?: { title?: string | null } | null
  type?: string | null
  status?: string | null
  title?: string | null
}): string | null {
  if (jobHasAlbumDesk(job)) {
    return job.source_job_id ?? job.id
  }
  const childId = job.preview_job_id?.trim()
  return childId || null
}

export function childHasAlbumDesk(child: JobChild): boolean {
  if (child.preview?.title?.trim()) {
    return true
  }
  // Summary rows may expose title without embedding full preview JSON.
  if (child.type === 'preview') {
    const title = child.title?.trim()
    return Boolean(title && !isHostnameLabel(title))
  }
  return false
}

export function jobPhotoCount(job: {
  type?: JobType | null
  preview?: { items?: readonly unknown[] } | null
  item_count?: number | null
}): number | null {
  if (job.type === 'scrape') {
    return null
  }
  if (job.preview?.items) {
    return job.preview.items.length
  }
  if (typeof job.item_count === 'number' && job.item_count > 0) {
    return job.item_count
  }
  return null
}

export function jobPhotosUrl(job: {
  type?: JobType | null
  product_url?: string | null
}): string | null {
  if (job.type === 'scrape') {
    return null
  }
  const url = job.product_url?.trim() || ''
  return url || null
}
