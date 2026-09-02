import type {
  AlbumJournal,
  AlbumPreview,
  ImportOrigin,
  Job,
  JobChild,
  JobEvent,
  JobStatus,
  JobSummary,
  JobType,
  PreviewItem,
  PreviewItemKind,
} from '../api/types.ts'

export class PreviewItemBuilder {
  private readonly item: PreviewItem

  private constructor(item: PreviewItem) {
    this.item = item
  }

  static jpeg(overrides: Partial<PreviewItem> = {}): PreviewItemBuilder {
    return new PreviewItemBuilder({
      id: '20120802_01',
      relpath: 'hrimages/20120802_01hr.JPG',
      caption: 'יום ראשון',
      size_bytes: 12,
      last_modified: '2012-08-02T10:00:00',
      taken_on: '2012-08-02',
      ...overrides,
    })
  }

  static winter(overrides: Partial<PreviewItem> = {}): PreviewItemBuilder {
    return new PreviewItemBuilder({
      id: '20190115_01',
      relpath: 'hrimages/20190115_01hr.JPG',
      caption: 'שלג',
      size_bytes: 12,
      last_modified: '2019-01-15T00:00:00',
      taken_on: '2019-01-15',
      ...overrides,
    })
  }

  static video(overrides: Partial<PreviewItem> = {}): PreviewItemBuilder {
    return new PreviewItemBuilder({
      id: 'clip01',
      relpath: 'hrimages/clip01hr.wmv',
      caption: 'סרטון',
      size_bytes: 48,
      last_modified: '2012-08-02T12:00:00',
      taken_on: '2012-08-02',
      kind: 'video',
      thumb_relpath: 'thumbnails/TN_clip01.jpg',
      play_relpath: 'hrimages/clip01hr.wmv',
      ...overrides,
    })
  }

  withId(id: string): this {
    this.item.id = id
    return this
  }

  withCaption(caption: string): this {
    this.item.caption = caption
    return this
  }

  withKind(kind: PreviewItemKind | string | null): this {
    this.item.kind = kind
    return this
  }

  withDates(takenOn: string | null, lastModified: string | null): this {
    this.item.taken_on = takenOn
    this.item.last_modified = lastModified
    return this
  }

  build(): PreviewItem {
    return { ...this.item }
  }
}

export class AlbumPreviewBuilder {
  private readonly preview: AlbumPreview

  private constructor(preview: AlbumPreview) {
    this.preview = preview
  }

  static empty(overrides: Partial<AlbumPreview> = {}): AlbumPreviewBuilder {
    return new AlbumPreviewBuilder({
      title: 'אלבום',
      description: null,
      multi_index: false,
      journal: null,
      items: [],
      ...overrides,
    })
  }

  static summer(overrides: Partial<AlbumPreview> = {}): AlbumPreviewBuilder {
    return new AlbumPreviewBuilder({
      title: 'קיץ 2012',
      description: 'תיאור גלריה',
      multi_index: false,
      journal: { heading: 'יומן קיץ', paragraphs: ['פסקה'] },
      items: [PreviewItemBuilder.jpeg().build()],
      ...overrides,
    })
  }

  static winter(overrides: Partial<AlbumPreview> = {}): AlbumPreviewBuilder {
    return new AlbumPreviewBuilder({
      title: 'חורף 2019',
      description: null,
      multi_index: false,
      journal: null,
      items: [PreviewItemBuilder.winter().build()],
      ...overrides,
    })
  }

  withTitle(title: string): this {
    this.preview.title = title
    return this
  }

  withDescription(description: string | null): this {
    this.preview.description = description
    return this
  }

  withJournal(journal: AlbumJournal | null): this {
    this.preview.journal = journal
    return this
  }

  withItems(...items: PreviewItem[]): this {
    this.preview.items = items
    return this
  }

  addItem(item: PreviewItem): this {
    this.preview.items = [...this.preview.items, item]
    return this
  }

  build(): AlbumPreview {
    return {
      ...this.preview,
      journal: this.preview.journal ? { ...this.preview.journal } : null,
      items: this.preview.items.map((item) => ({ ...item })),
    }
  }
}

export class JobBuilder {
  private readonly job: Job

  private constructor(job: Job) {
    this.job = job
  }

  static preview(overrides: Partial<Job> = {}): JobBuilder {
    return new JobBuilder({
      id: 'job-winter',
      status: 'done',
      type: 'preview',
      error: null,
      product_url: null,
      folder_label: 'SkiTrip',
      preview: AlbumPreviewBuilder.winter().build(),
      ...overrides,
    })
  }

  static summer(overrides: Partial<Job> = {}): JobBuilder {
    return new JobBuilder({
      id: 'job-summer',
      status: 'done',
      type: 'upload',
      error: null,
      product_url: 'https://photos.example/summer',
      folder_label: 'Day1',
      preview: AlbumPreviewBuilder.summer().build(),
      ...overrides,
    })
  }

  static scrape(overrides: Partial<Job> = {}): JobBuilder {
    return new JobBuilder({
      id: 'scrape-1',
      status: 'running',
      type: 'scrape',
      error: null,
      product_url: null,
      preview: null,
      url: 'https://gallery.example/index.html',
      children: [],
      ...overrides,
    })
  }

  withId(id: string): this {
    this.job.id = id
    return this
  }

  withStatus(status: JobStatus): this {
    this.job.status = status
    return this
  }

  withType(type: JobType): this {
    this.job.type = type
    return this
  }

  withPreview(preview: AlbumPreview | null): this {
    this.job.preview = preview
    return this
  }

  withProductUrl(url: string | null): this {
    this.job.product_url = url
    return this
  }

  withImportOrigin(origin: ImportOrigin): this {
    this.job.import_origin = origin
    return this
  }

  withNumber(number: number): this {
    this.job.number = number
    return this
  }

  asSummary(overrides: Partial<JobSummary> = {}): JobSummary {
    const preview = this.job.preview
    return {
      id: this.job.id,
      number: this.job.number,
      status: this.job.status,
      type: this.job.type,
      error: this.job.error,
      error_code: this.job.error_code,
      warnings: this.job.warnings,
      title: preview?.title ?? null,
      item_count: preview?.items.length ?? 0,
      created_at: this.job.created_at ?? null,
      product_url: this.job.product_url,
      folder_label: this.job.folder_label,
      updated_at: this.job.updated_at,
      finished_at: this.job.finished_at,
      source_job_id: this.job.source_job_id,
      preview_job_id: this.job.preview_job_id,
      scrape_url: this.job.scrape_url,
      auto_publish: this.job.auto_publish,
      user_edited: this.job.user_edited,
      import_origin: this.job.import_origin,
      ...overrides,
    }
  }

  build(): Job {
    return {
      ...this.job,
      preview: this.job.preview
        ? AlbumPreviewBuilder.empty(this.job.preview).build()
        : null,
      children: this.job.children?.map((child) => ({ ...child })),
    }
  }
}

export class JobSummaryBuilder {
  private readonly summary: JobSummary

  private constructor(summary: JobSummary) {
    this.summary = summary
  }

  static from(summary: JobSummary): JobSummaryBuilder {
    return new JobSummaryBuilder({ ...summary })
  }

  static summer(overrides: Partial<JobSummary> = {}): JobSummaryBuilder {
    return new JobSummaryBuilder({
      id: 'job-summer',
      status: 'done',
      type: 'upload',
      error: null,
      title: 'קיץ 2012',
      item_count: 3,
      created_at: '2012-08-02T10:00:00+00:00',
      product_url: 'https://photos.example/summer',
      folder_label: 'Day1',
      ...overrides,
    })
  }

  static winter(overrides: Partial<JobSummary> = {}): JobSummaryBuilder {
    return new JobSummaryBuilder({
      id: 'job-winter',
      status: 'done',
      type: 'preview',
      error: null,
      title: 'חורף 2019',
      item_count: 1,
      created_at: '2019-01-15T00:00:00+00:00',
      product_url: null,
      folder_label: 'SkiTrip',
      ...overrides,
    })
  }

  static scrapeHost(overrides: Partial<JobSummary> = {}): JobSummaryBuilder {
    return new JobSummaryBuilder({
      id: 'job-scrape-host',
      status: 'done',
      type: 'scrape',
      error: null,
      title: 'albums.example',
      item_count: 0,
      created_at: '2026-08-08T00:00:00+00:00',
      product_url: null,
      folder_label: 'albums.example',
      ...overrides,
    })
  }

  withId(id: string): this {
    this.summary.id = id
    return this
  }

  withStatus(status: JobStatus): this {
    this.summary.status = status
    return this
  }

  build(): JobSummary {
    return { ...this.summary }
  }
}

export class JobEventBuilder {
  private readonly event: JobEvent

  private constructor(event: JobEvent) {
    this.event = event
  }

  static ingest(overrides: Partial<JobEvent> = {}): JobEventBuilder {
    return new JobEventBuilder({
      job_id: 'job-summer',
      stage: 'ingest',
      message: 'Writing upload',
      current: 0,
      total: 1,
      extra: null,
      occurred_at: '2012-08-02T10:00:00+00:00',
      ...overrides,
    })
  }

  static previewReady(overrides: Partial<JobEvent> = {}): JobEventBuilder {
    return new JobEventBuilder({
      job_id: 'job-summer',
      stage: 'preview_ready',
      message: 'קיץ 2012',
      current: 1,
      total: 1,
      extra: null,
      occurred_at: '2012-08-02T10:01:00+00:00',
      ...overrides,
    })
  }

  withJobId(jobId: string): this {
    this.event.job_id = jobId
    return this
  }

  withStage(stage: string): this {
    this.event.stage = stage
    return this
  }

  build(): JobEvent {
    return { ...this.event }
  }
}

export class JobChildBuilder {
  private readonly child: JobChild

  private constructor(child: JobChild) {
    this.child = child
  }

  static scrape(overrides: Partial<JobChild> = {}): JobChildBuilder {
    return new JobChildBuilder({
      id: 'child-scrape',
      number: 8,
      status: 'pending',
      type: 'scrape',
      scrape_url: 'https://albums.example/day2',
      ...overrides,
    })
  }

  static preview(overrides: Partial<JobChild> = {}): JobChildBuilder {
    return new JobChildBuilder({
      id: 'child-preview',
      number: 9,
      status: 'running',
      type: 'preview',
      title: 'Day 2',
      ...overrides,
    })
  }

  build(): JobChild {
    return { ...this.child }
  }
}

export const SAMPLE_SETTINGS = {
  max_concurrent_jobs: 2,
  pending: 0,
  running: 0,
  waiting: 0,
} as const
