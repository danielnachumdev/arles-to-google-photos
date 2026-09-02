export type JobStatus = 'pending' | 'running' | 'waiting' | 'done' | 'failed' | 'cancelled'

export type JobType = 'preview' | 'upload' | 'scrape'

export type ImportOrigin = 'folder' | 'web'

export type PreviewItemKind = 'image' | 'video'

export type PreviewItem = {
  id: string
  relpath: string
  caption: string
  size_bytes: number
  last_modified: string | null
  taken_on: string | null
  kind?: PreviewItemKind | string | null
  thumb_relpath?: string | null
  play_relpath?: string | null
}

export type AlbumJournal = {
  heading: string | null
  paragraphs: string[]
}

export type AlbumPreview = {
  title: string
  description: string | null
  multi_index: boolean
  journal: AlbumJournal | null
  items: PreviewItem[]
  /** True when folder media was imported without a full Arles HTML layout. */
  structure_fallback?: boolean | null
}

export type JobChild = {
  id: string
  number?: number | null
  status?: JobStatus
  type?: JobType
  error?: string | null
  error_code?: string | null
  title?: string | null
  item_count?: number | null
  product_url?: string | null
  preview?: AlbumPreview | null
  url?: string | null
  scrape_url?: string | null
  folder_label?: string | null
  created_at?: string | null
  parent_job_id?: string | null
  import_origin?: ImportOrigin | null
}

export type Job = {
  id: string
  number?: number | null
  status: JobStatus
  type: JobType
  error: string | null
  error_code?: string | null
  warnings?: string[] | null
  preview: AlbumPreview | null
  product_url: string | null
  created_at?: string | null
  started_at?: string | null
  running_started_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  duration_seconds?: number | null
  folder_label?: string | null
  source_job_id?: string | null
  parent_job_id?: string | null
  url?: string | null
  scrape_url?: string | null
  headers?: Record<string, string> | null
  header_names?: string[] | null
  has_headers?: boolean
  children?: JobChild[]
  child_ids?: string[]
  preview_job_id?: string | null
  auto_publish?: boolean
  user_edited?: boolean
  import_origin?: ImportOrigin | null
  archived_at?: string | null
}

export type ScrapeJobRequest = {
  url: string
  headers?: Record<string, string>
  auto_publish?: boolean
  access_token?: string
}

export type JobChildrenResponse = {
  children?: JobChild[]
  jobs?: JobChild[]
}

export type JobSummary = {
  id: string
  number?: number | null
  status: JobStatus
  type: JobType
  error: string | null
  error_code?: string | null
  warnings?: string[] | null
  title: string | null
  item_count: number
  created_at: string | null
  started_at?: string | null
  running_started_at?: string | null
  product_url: string | null
  folder_label?: string | null
  updated_at?: string | null
  finished_at?: string | null
  duration_seconds?: number | null
  last_stage?: string | null
  source_job_id?: string | null
  preview_job_id?: string | null
  scrape_url?: string | null
  auto_publish?: boolean
  user_edited?: boolean
  import_origin?: ImportOrigin | null
  archived_at?: string | null
}

export type JobArchiveResult = {
  job: Job
  archived_ids: string[]
}

export type JobCancelPreview = {
  job?: JobChild | JobSummary
  descendants: JobChild[]
}

export type RestartMode = 'all' | 'remaining'

export type ReprocessMode = 'overwrite' | 'new'

export type ReprocessOptions = {
  mode?: ReprocessMode
  titlePrefix?: string
}

export type JobRestartPreview = {
  job?: JobChild | JobSummary
  descendants: JobChild[]
  done: JobChild[]
  remaining: JobChild[]
}

export type JobListResponse = {
  jobs: JobSummary[]
}

export type JobFile = {
  relpath: string
  blob: Blob
  lastModifiedMs?: number
}

export type JobEdits = {
  title?: string
  description?: string
  journal?: AlbumJournal | null
  captions?: Record<string, string>
}

export type JobEventKind = 'log' | 'lifecycle' | 'progress'

export type JobEventAudience = 'ui' | 'ops'

export type JobEvent = {
  job_id: string
  stage: string
  message: string
  current: number
  total: number
  extra: Record<string, unknown> | null
  occurred_at?: string | null
  kind?: JobEventKind | null
  audience?: JobEventAudience | null
}

export type JobHistoryResponse = {
  events: JobEvent[]
}

export type OrchestratorSettings = {
  max_concurrent_jobs: number
  pending: number
  running: number
  waiting: number
}
