import type {
  Job,
  JobArchiveResult,
  JobCancelPreview,
  JobRestartPreview,
  JobChild,
  RestartMode,
  JobChildrenResponse,
  JobEdits,
  JobEvent,
  JobFile,
  JobHistoryResponse,
  JobListResponse,
  JobSummary,
  OrchestratorSettings,
  ReprocessOptions,
  ScrapeJobRequest,
} from './types.ts'
import { apiErrorFromHttp } from '../lib/formatApiError.ts'
import {
  postFormData,
  type StoreProgressEvent,
  type UploadProgressEvent,
} from './xhrFormPost.ts'

export type { StoreProgressEvent, UploadProgressEvent }

export class AlbumExistsError extends Error {
  readonly existingId: string
  readonly title: string
  readonly code = 'album_exists' as const

  constructor(existingId: string, title: string) {
    super(`Album already exists: ${title}`)
    this.name = 'AlbumExistsError'
    this.existingId = existingId
    this.title = title
  }
}

function isAlbumExistsDetail(
  value: unknown,
): value is { code: 'album_exists'; existing_id: string; title: string } {
  if (!value || typeof value !== 'object') {
    return false
  }
  const detail = value as Record<string, unknown>
  return (
    detail.code === 'album_exists' &&
    typeof detail.existing_id === 'string' &&
    typeof detail.title === 'string'
  )
}

async function throwHttpError(response: Response): Promise<never> {
  const body = await response.text()
  throw apiErrorFromHttp(response.status, body)
}

function throwStatusBody(status: number, bodyText: string): never {
  throw apiErrorFromHttp(status, bodyText)
}

export class MigrationClient {
  private readonly baseUrl: string

  constructor(baseUrl = '/api') {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  async createJob(
    files: JobFile[],
    options?: {
      overwrite?: boolean
      autoPublish?: boolean
      accessToken?: string
      onUploadProgress?: (event: UploadProgressEvent) => void
      onStoreProgress?: (event: StoreProgressEvent) => void
    },
  ): Promise<Job> {
    const form = new FormData()
    let anyMtime = false

    for (const file of files) {
      form.append(
        'files',
        new File([file.blob], file.relpath, {
          type: file.blob.type || 'application/octet-stream',
        }),
      )
      if (file.lastModifiedMs !== undefined) {
        anyMtime = true
      }
    }

    if (anyMtime) {
      for (const file of files) {
        form.append(
          'lastModified',
          file.lastModifiedMs !== undefined ? String(file.lastModifiedMs) : '',
        )
      }
    }

    if (options?.accessToken) {
      form.append('access_token', options.accessToken)
    }

    const params = new URLSearchParams()
    if (options?.overwrite) {
      params.set('overwrite', 'true')
    }
    if (options?.autoPublish) {
      params.set('auto_publish', 'true')
    }
    const query = params.toString() ? `?${params.toString()}` : ''
    const { status, bodyText } = await postFormData(`${this.baseUrl}/jobs${query}`, form, {
      onProgress: options?.onUploadProgress,
      onStoreProgress: options?.onStoreProgress,
      // Cloud may stream durable-put progress after the browser upload hits 100%.
      streamStoreProgress: Boolean(options?.onStoreProgress),
    })

    if (status === 409) {
      try {
        const parsed = JSON.parse(bodyText) as { detail?: unknown }
        if (isAlbumExistsDetail(parsed.detail)) {
          throw new AlbumExistsError(parsed.detail.existing_id, parsed.detail.title)
        }
      } catch (err) {
        if (err instanceof AlbumExistsError) {
          throw err
        }
      }
      throwStatusBody(409, bodyText)
    }
    if (status < 200 || status >= 300) {
      throwStatusBody(status, bodyText)
    }
    return JSON.parse(bodyText) as Job
  }

  async createScrapeJob(input: ScrapeJobRequest): Promise<Job> {
    const body: ScrapeJobRequest = { url: input.url }
    if (input.headers && Object.keys(input.headers).length > 0) {
      body.headers = input.headers
    }
    if (input.auto_publish) {
      body.auto_publish = true
    }
    if (input.access_token) {
      body.access_token = input.access_token
    }
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
  }

  async listJobs(options?: { dedupe?: boolean }): Promise<JobSummary[]> {
    const response = await fetch(
      `${this.baseUrl}/jobs${options?.dedupe ? '?dedupe=true' : ''}`,
      { method: 'GET' },
    )
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as JobListResponse
    return payload.jobs ?? []
  }

  async getJob(id: string): Promise<Job> {
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}`, {
        method: 'GET',
      }),
    )
  }

  async listJobChildren(id: string): Promise<JobChild[]> {
    const response = await fetch(
      `${this.baseUrl}/jobs/${encodeURIComponent(id)}/children`,
      { method: 'GET' },
    )
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as JobChildrenResponse | JobChild[]
    if (Array.isArray(payload)) {
      return payload
    }
    return payload.children ?? payload.jobs ?? []
  }

  async getCancelPreview(id: string): Promise<JobCancelPreview> {
    const response = await fetch(
      `${this.baseUrl}/jobs/${encodeURIComponent(id)}/cancel-preview`,
      { method: 'GET' },
    )
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as {
      job?: JobChild | JobSummary
      descendants?: JobChild[]
    }
    return {
      job: payload.job,
      descendants: Array.isArray(payload.descendants) ? payload.descendants : [],
    }
  }

  async getJobHistory(
    id: string,
    options?: { audience?: 'ui' | 'ops' | 'all' },
  ): Promise<JobEvent[]> {
    const query = options?.audience
      ? `?audience=${encodeURIComponent(options.audience)}`
      : ''
    const response = await fetch(
      `${this.baseUrl}/jobs/${encodeURIComponent(id)}/history${query}`,
      { method: 'GET' },
    )
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as JobHistoryResponse
    return payload.events ?? []
  }

  async patchJob(id: string, edits: JobEdits): Promise<Job> {
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(edits),
      }),
    )
  }

  async publishJob(id: string, accessToken: string): Promise<Job> {
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: accessToken }),
      }),
    )
  }

  async reprocessJob(id: string, options?: ReprocessOptions): Promise<Job> {
    const payload: Record<string, unknown> = {}
    if (options?.mode) {
      payload.mode = options.mode
    }
    if (options?.titlePrefix != null) {
      payload.title_prefix = options.titlePrefix
    }
    const hasBody = Object.keys(payload).length > 0
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}/reprocess`, {
        method: 'POST',
        headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
        body: hasBody ? JSON.stringify(payload) : undefined,
      }),
    )
  }

  async getRestartPreview(id: string): Promise<JobRestartPreview> {
    const response = await fetch(
      `${this.baseUrl}/jobs/${encodeURIComponent(id)}/restart-preview`,
      { method: 'GET' },
    )
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as {
      job?: JobChild | JobSummary
      descendants?: JobChild[]
      done?: JobChild[]
      remaining?: JobChild[]
    }
    return {
      job: payload.job,
      descendants: Array.isArray(payload.descendants) ? payload.descendants : [],
      done: Array.isArray(payload.done) ? payload.done : [],
      remaining: Array.isArray(payload.remaining) ? payload.remaining : [],
    }
  }

  async restartJob(
    id: string,
    options?: { accessToken?: string; mode?: RestartMode },
  ): Promise<Job> {
    const body: { access_token?: string; mode?: RestartMode } = {}
    if (options?.accessToken) {
      body.access_token = options.accessToken
    }
    if (options?.mode) {
      body.mode = options.mode
    }
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}/restart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    )
  }

  async cancelJob(id: string): Promise<Job> {
    return this.readJob(
      await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}/cancel`, {
        method: 'POST',
      }),
    )
  }

  async archiveJob(id: string): Promise<JobArchiveResult> {
    const response = await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}/archive`, {
      method: 'POST',
    })
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as Partial<JobArchiveResult> & Job
    if (payload.job && Array.isArray(payload.archived_ids)) {
      return { job: payload.job, archived_ids: payload.archived_ids }
    }
    return { job: payload as Job, archived_ids: [id] }
  }

  async deleteJob(id: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/jobs/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
    if (!response.ok) {
      await throwHttpError(response)
    }
  }

  async getSettings(): Promise<OrchestratorSettings> {
    const response = await fetch(`${this.baseUrl}/settings`, { method: 'GET' })
    if (!response.ok) {
      await throwHttpError(response)
    }
    return (await response.json()) as OrchestratorSettings
  }

  async getVersion(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/version`, { method: 'GET' })
    if (!response.ok) {
      await throwHttpError(response)
    }
    const payload = (await response.json()) as { version?: unknown }
    const version = typeof payload.version === 'string' ? payload.version.trim() : ''
    if (!version) {
      throw new Error('version missing')
    }
    return version
  }

  async patchSettings(maxConcurrentJobs: number): Promise<OrchestratorSettings> {
    const response = await fetch(`${this.baseUrl}/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_concurrent_jobs: maxConcurrentJobs }),
    })
    if (!response.ok) {
      await throwHttpError(response)
    }
    return (await response.json()) as OrchestratorSettings
  }

  mediaUrl(
    jobId: string,
    itemId: string,
    variant?: 'original' | 'thumb' | 'play',
  ): string {
    const path = `${this.baseUrl}/jobs/${encodeURIComponent(jobId)}/media/${encodeURIComponent(itemId)}`
    if (!variant || variant === 'original') {
      return path
    }
    return `${path}?variant=${encodeURIComponent(variant)}`
  }

  private async readJob(response: Response): Promise<Job> {
    if (!response.ok) {
      await throwHttpError(response)
    }
    return (await response.json()) as Job
  }
}
