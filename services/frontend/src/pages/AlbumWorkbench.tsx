import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link, useBlocker, useNavigate } from 'react-router-dom'
import {
  AlbumExistsError,
  MigrationClient,
  type StoreProgressEvent,
  type UploadProgressEvent,
} from '../api/client.ts'
import { JobEventSource } from '../api/events.ts'
import type { Job, JobEvent, JobType, ReprocessOptions } from '../api/types.ts'
import { CancelJobDialog } from '../components/CancelJobDialog.tsx'
import { ConfirmDialog } from '../components/ConfirmDialog.tsx'
import { ReprocessConflictDialog } from '../components/ReprocessConflictDialog.tsx'
import { ImagePreviewModal, type ImagePreviewTarget } from '../components/ImagePreviewModal.tsx'
import { ImportDesk } from '../components/ImportDesk.tsx'
import { LoadingSpinner } from '../components/LoadingSpinner.tsx'
import { ModifiedMark } from '../components/ModifiedMark.tsx'
import { PreviewCard } from '../components/PreviewCard.tsx'
import { jobFilesFromDirectory } from '../lib/collectFolder.ts'
import { explainCaughtError, isNotFoundError } from '../lib/formatApiError.ts'
import {
  albumDeskJobId,
  inferImportOrigin,
  jobErrorMessage,
  jobHasAlbumDesk,
} from '../lib/jobFields.ts'
import { GoogleAuthCancelledError, requestGooglePhotosAccessToken } from '../lib/googleAuth.ts'
import { withGooglePhotosAccessToken } from '../lib/withGooglePhotosToken.ts'
import { isJobCancellable } from '../lib/formatJobDuration.ts'
import { jobStatusLabel, jobTypeLabel, t } from '../lib/language.ts'
import { computePreviewDirty } from '../lib/previewDirty.ts'
import { previewItemKind, videoHasBrowserPlayableCopy } from '../lib/previewMedia.ts'
import { isLifecycleJobEvent, isOpsJobEvent, jobLogMessage } from '../lib/jobLogs.ts'
import { announceRunSubmitted, kindFromJobType, trackRun } from '../lib/runTracker.ts'
import { toast } from '../lib/toast.ts'
import { NotFoundPage } from './NotFoundPage.tsx'
import './AlbumWorkbench.css'

const client = new MigrationClient()
const events = new JobEventSource()

type Phase = 'pick' | 'working' | 'preview' | 'failed'

type TransferProgress =
  | ({ phase: 'upload' } & UploadProgressEvent)
  | ({ phase: 'store' } & StoreProgressEvent)

function formatUploadBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return '0 B'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function explainFailure(
  action: 'preview' | 'save' | 'publish' | 'reprocess' | 'history',
  err: unknown,
): string {
  return explainCaughtError(err, (detail) => {
    if (action === 'preview') {
      return t.errorPreview(detail)
    }
    if (action === 'save') {
      return t.errorSave(detail)
    }
    if (action === 'reprocess') {
      return t.errorReprocess(detail)
    }
    if (action === 'history') {
      return t.errorHistory(detail)
    }
    return t.errorPublish(detail)
  })
}

export function AlbumWorkbench({
  jobId,
  onJobCreated,
}: {
  jobId?: string
  onJobCreated?: (id: string, type?: JobType) => void
}) {
  const navigate = useNavigate()
  const folderId = useId()
  const fieldIds = useId()
  const [files, setFiles] = useState<FileList | null>(null)
  const [folderLabel, setFolderLabel] = useState('')
  const [phase, setPhase] = useState<Phase>(jobId ? 'working' : 'pick')
  const [statusLine, setStatusLine] = useState(jobId ? t.loadingAlbum : '')
  const [uploadProgress, setUploadProgress] = useState<TransferProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [journalHeading, setJournalHeading] = useState('')
  const [journalBody, setJournalBody] = useState('')
  const [captions, setCaptions] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)
  const [reprocessOpen, setReprocessOpen] = useState(false)
  const [existingAlbum, setExistingAlbum] = useState<{ id: string; title: string } | null>(null)
  const [previewTarget, setPreviewTarget] = useState<ImagePreviewTarget | null>(null)
  const [uploadRun, setUploadRun] = useState<Job | null>(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const publishWatchRef = useRef<(() => void) | undefined>(undefined)
  const pendingImportRef = useRef<{ autoPublish: boolean; accessToken?: string } | null>(null)

  const count = files?.length ?? 0
  const items = job?.preview?.items ?? []
  const photosUrl = uploadRun?.product_url || job?.product_url || null
  const published =
    (uploadRun?.type === 'upload' && uploadRun.status === 'done') ||
    (job?.type === 'upload' && job.status === 'done') ||
    Boolean(job?.product_url)
  const publishInProgress =
    publishing ||
    uploadRun?.status === 'running' ||
    (job?.type === 'upload' && job.status === 'running')
  const busy = saving || publishing || reprocessing || phase === 'working'
  const cancelTarget =
    uploadRun && isJobCancellable(uploadRun.status)
      ? uploadRun
      : job && isJobCancellable(job.status)
        ? job
        : null

  useEffect(() => {
    return () => {
      publishWatchRef.current?.()
    }
  }, [])
  const showFolderPick = !jobId
  const dirtyState = computePreviewDirty(job?.preview, {
    title,
    description,
    journalHeading,
    journalBody,
    captions,
  })
  const dirty = Boolean(job?.preview) && dirtyState.dirty
  const reprocessConflict = dirty || Boolean(job?.user_edited)
  const blocker = useBlocker(
    useCallback(
      ({ currentLocation, nextLocation }) =>
        dirty && currentLocation.pathname !== nextLocation.pathname,
      [dirty],
    ),
  )

  useEffect(() => {
    if (!dirty) {
      return
    }
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
    }
  }, [dirty])

  function applyJob(next: Job) {
    setJob(next)
    if (!next.preview) {
      return
    }
    setTitle(next.preview.title)
    setDescription(next.preview.description ?? '')
    setJournalHeading(next.preview.journal?.heading ?? '')
    setJournalBody((next.preview.journal?.paragraphs ?? []).join('\n\n'))
    setCaptions(Object.fromEntries(next.preview.items.map((item) => [item.id, item.caption])))
  }

  useEffect(() => {
    if (!jobId) {
      return
    }
    const previous = document.title
    const label = title.trim() || job?.folder_label?.trim() || jobId
    document.title = t.albumDocumentTitle(label)
    return () => {
      document.title = previous
    }
  }, [jobId, title, job?.folder_label])

  useEffect(() => {
    if (!jobId) {
      return
    }
    const id = jobId
    let cancelled = false
    async function load() {
      setError(null)
      setNotFound(false)
      setPreviewTarget(null)
      setPhase('working')
      setStatusLine(t.loadingAlbum)
      try {
        const next = await client.getJob(id)
        if (cancelled) {
          return
        }
        applyJob(next)
        setUploadRun(null)
        if (!jobHasAlbumDesk(next) && next.status !== 'pending' && next.status !== 'running') {
          const deskId = albumDeskJobId(next)
          if (deskId && deskId !== next.id) {
            navigate(`/albums/${deskId}`, { replace: true })
            return
          }
        }
        if (next.preview) {
          setPhase('preview')
          setStatusLine(t.previewReady)
        } else if (next.status === 'pending' || next.status === 'running') {
          setPhase('working')
          setStatusLine(t.preparing)
        } else if (next.error || next.error_code || next.status === 'failed' || next.status === 'cancelled') {
          setPhase('failed')
          setStatusLine('')
          setError(
            next.status === 'cancelled'
              ? t.toastRunCancelled
              : jobErrorMessage(next) || next.error || t.toastRunCancelled,
          )
        } else {
          setPhase('failed')
          setStatusLine('')
        }
      } catch (err) {
        if (cancelled) {
          return
        }
        if (isNotFoundError(err)) {
          setNotFound(true)
          setJob(null)
          setPhase('failed')
          setStatusLine('')
          setError(null)
        } else {
          setPhase('failed')
          setError(explainFailure('history', err))
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) {
      return
    }
    const inflight =
      job?.status === 'pending' ||
      job?.status === 'running' ||
      job?.status === 'waiting'
    const waitingForFirstPreview = !job?.preview && (!job || inflight)
    const reprocessingExisting = Boolean(job?.preview && inflight)
    if (!waitingForFirstPreview && !reprocessingExisting) {
      return
    }
    const intervalId = window.setInterval(() => {
      void client
        .getJob(jobId)
        .then((next) => {
          applyJob(next)
          if (
            !jobHasAlbumDesk(next) &&
            next.status !== 'pending' &&
            next.status !== 'running'
          ) {
            const deskId = albumDeskJobId(next)
            if (deskId && deskId !== next.id) {
              navigate(`/albums/${deskId}`, { replace: true })
              return
            }
          }
          if (next.status === 'failed' || next.status === 'cancelled') {
            setPhase('failed')
            setError(
              next.status === 'cancelled'
                ? t.toastRunCancelled
                : jobErrorMessage(next) || next.error || t.toastRunCancelled,
            )
            return
          }
          if (next.preview && next.status === 'done') {
            setPhase('preview')
            setStatusLine(t.previewReady)
            return
          }
          if (!next.preview) {
            setPhase('working')
            setStatusLine(t.preparing)
          }
        })
        .catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(intervalId)
  }, [jobId, job?.preview, job?.status])

  useEffect(() => {
    if (!jobId || !job || job.type !== 'preview') {
      return
    }
    let cancelled = false
    void client
      .listJobs()
      .then((jobs) => {
        if (cancelled) {
          return
        }
        const related = jobs
          .filter((item) => item.type === 'upload' && item.source_job_id === jobId)
          .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
        const latest = related[0]
        if (!latest) {
          return
        }
        setUploadRun((prev) => {
          if (prev && prev.id === latest.id) {
            return prev
          }
          return {
            id: latest.id,
            status: latest.status,
            type: latest.type,
            error: latest.error,
            product_url: latest.product_url,
            preview: job.preview,
            created_at: latest.created_at,
            folder_label: latest.folder_label,
            source_job_id: latest.source_job_id,
          }
        })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [jobId, job])

  function onFolder(list: FileList | null) {
    setFiles(list)
    const first = list?.item(0) as (File & { webkitRelativePath?: string }) | null
    const rel = first?.webkitRelativePath || first?.name || ''
    setFolderLabel(rel.split(/[/\\]/)[0] || '')
    setPhase('pick')
    setJob(null)
    setError(null)
    setStatusLine('')
    setPublishing(false)
    setReprocessing(false)
    setReprocessOpen(false)
    setExistingAlbum(null)
    setPreviewTarget(null)
    setUploadRun(null)
  }

  async function requestImportToken(autoPublish: boolean): Promise<string | undefined> {
    if (!autoPublish) {
      return undefined
    }
    setStatusLine(t.signingInGoogle)
    try {
      return await requestGooglePhotosAccessToken()
    } catch (err) {
      if (err instanceof GoogleAuthCancelledError) {
        setPhase('pick')
        setStatusLine('')
        setError(t.signInCancelled)
        toast.warning(t.signInCancelled)
        return undefined
      }
      setPhase('pick')
      setStatusLine('')
      const message = explainFailure('publish', err)
      setError(message)
      toast.bad(message)
      return undefined
    }
  }

  async function trackUploadChildren(parentId: string) {
    try {
      const children = await client.listJobChildren(parentId)
      for (const child of children) {
        if (child.type !== 'upload') {
          continue
        }
        announceRunSubmitted(child.id, child.number)
        trackRun({
          id: child.id,
          kind: 'upload',
          status: child.status ?? 'running',
          error: child.error,
          number: child.number,
        })
      }
    } catch {
      return
    }
  }

  async function uploadPreview(payload: ReturnType<typeof jobFilesFromDirectory>, overwrite = false) {
    const pending = pendingImportRef.current
    setPhase('working')
    setError(null)
    setUploadProgress({ phase: 'upload', loaded: 0, total: 0, percent: 0 })
    setStatusLine(t.sendingFiles(payload.length))
    try {
      const created = await client.createJob(payload, {
        ...(overwrite ? { overwrite: true } : {}),
        autoPublish: pending?.autoPublish,
        accessToken: pending?.accessToken,
        onUploadProgress: (event) => {
          setUploadProgress({ phase: 'upload', ...event })
          setStatusLine(
            event.total > 0
              ? t.sendingFilesProgress(payload.length, event.percent)
              : t.sendingFiles(payload.length),
          )
        },
        onStoreProgress: (event) => {
          setUploadProgress({ phase: 'store', ...event })
          setStatusLine(
            event.total > 0
              ? t.storingFilesProgress(event.current, event.total, event.percent)
              : t.storingFiles,
          )
        },
      })
      setUploadProgress(null)
      announceRunSubmitted(created.id, created.number)
      trackRun({
        id: created.id,
        kind: 'preview',
        status: created.status,
        error: created.error,
        number: created.number,
      })
      if (pending?.autoPublish) {
        await trackUploadChildren(created.id)
      }
      if (onJobCreated) {
        onJobCreated(created.id, created.type)
        return
      }
      applyJob(created)
      if (created.preview) {
        setPhase('preview')
        setStatusLine(t.previewReady)
      } else {
        setPhase('working')
        setStatusLine(t.preparing)
      }
    } catch (err) {
      setUploadProgress(null)
      if (err instanceof AlbumExistsError) {
        setPhase('pick')
        setStatusLine('')
        setExistingAlbum({ id: err.existingId, title: err.title })
        return
      }
      setPhase('failed')
      setError(overwrite ? explainCaughtError(err, t.errorOverwrite) : explainFailure('preview', err))
    }
  }

  async function importFromWeb(
    url: string,
    headers?: Record<string, string>,
    autoPublish = false,
  ) {
    const accessToken = await requestImportToken(autoPublish)
    if (autoPublish && !accessToken) {
      return
    }
    setPhase('working')
    setError(null)
    setStatusLine(t.importingWeb)
    try {
      const created = await client.createScrapeJob({
        url,
        headers,
        ...(autoPublish ? { auto_publish: true, access_token: accessToken } : {}),
      })
      announceRunSubmitted(created.id, created.number)
      trackRun({
        id: created.id,
        kind: kindFromJobType(created.type),
        status: created.status,
        error: created.error,
        error_code: created.error_code,
        scrape_url: created.scrape_url || created.url,
        number: created.number,
      })
      if (onJobCreated) {
        onJobCreated(created.id, created.type)
        return
      }
      setJob(created)
      setPhase(created.status === 'failed' ? 'failed' : 'pick')
      setStatusLine('')
      if (created.error || created.error_code) {
        setError(jobErrorMessage(created))
      }
    } catch (err) {
      setPhase('failed')
      setError(explainCaughtError(err, t.errorScrape))
    }
  }

  async function cancelActiveRun() {
    if (!cancelTarget || cancelling) {
      return
    }
    setCancelling(true)
    setCancelOpen(false)
    setError(null)
    try {
      const next = await client.cancelJob(cancelTarget.id)
      if (uploadRun && next.id === uploadRun.id) {
        setUploadRun(next)
        setPublishing(false)
        publishWatchRef.current?.()
        publishWatchRef.current = undefined
        setStatusLine(t.toastRunCancelled)
      }
      if (job && next.id === job.id) {
        setJob(next)
        setStatusLine(t.toastRunCancelled)
      }
    } catch (err) {
      setError(explainCaughtError(err, t.errorCancel))
    } finally {
      setCancelling(false)
    }
  }

  async function preparePreview(autoPublish = false) {
    const payload = jobFilesFromDirectory(files)
    if (payload.length === 0) {
      return
    }
    const accessToken = await requestImportToken(autoPublish)
    if (autoPublish && !accessToken) {
      return
    }
    pendingImportRef.current = { autoPublish, accessToken }
    await uploadPreview(payload)
  }

  async function confirmOverwrite() {
    const payload = jobFilesFromDirectory(files)
    setExistingAlbum(null)
    if (payload.length === 0) {
      return
    }
    await uploadPreview(payload, true)
  }

  async function saveEdits() {
    if (!job) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      const paragraphs = journalBody
        .split(/\n\s*\n/)
        .map((part) => part.trim())
        .filter(Boolean)
      const hadJournal = Boolean(job.preview?.journal || journalHeading.trim() || paragraphs.length)
      const next = await client.patchJob(job.id, {
        title,
        description,
        ...(hadJournal
          ? { journal: { heading: journalHeading.trim() || null, paragraphs } }
          : {}),
        captions,
      })
      applyJob(next)
      setStatusLine(t.saved)
      toast.good(t.saved)
    } catch (err) {
      const message = explainFailure('save', err)
      setError(message)
      toast.bad(message)
    } finally {
      setSaving(false)
    }
  }

  async function publishAlbum() {
    if (!job) {
      return
    }
    const sourceId = job.id
    const previousUploadId = uploadRun?.id
    setPublishing(true)
    setError(null)
    setStatusLine(t.signingInGoogle)
    let unsubscribe: (() => void) | undefined
    let publishRequested = false
    try {
      publishRequested = true
      const started = await withGooglePhotosAccessToken((accessToken) =>
        client.publishJob(sourceId, accessToken),
      )
      setStatusLine(t.publishingStatus)
      setUploadRun(started)
      announceRunSubmitted(started.id, started.number)
      trackRun({
        id: started.id,
        kind: 'upload',
        status: started.status,
        error: started.error,
        number: started.number,
      })
      const applyUploadResult = (latest: Job) => {
        setUploadRun(latest)
        if (latest.status === 'failed') {
          setError(latest.error || t.errorPublish('failed'))
          return
        }
        if (latest.status === 'cancelled') {
          setPublishing(false)
          setStatusLine(t.toastRunCancelled)
          return
        }
        if (latest.status === 'done') {
          setStatusLine(latest.product_url ? t.publishedStatus : t.publishedNoUrl)
        }
      }
      unsubscribe = events.subscribe(
        started.id,
        (event: JobEvent) => {
          if (!isOpsJobEvent(event)) {
            const denom = event.total > 0 ? ` ${event.current}/${event.total}` : ''
            const message = jobLogMessage(event, t.jobLogLifecycle)
            setStatusLine(`${message}${denom}`)
          }
          if (isLifecycleJobEvent(event)) {
            void client.getJob(started.id).then(applyUploadResult).catch(() => undefined)
          }
        },
        'publish',
      )
      publishWatchRef.current?.()
      publishWatchRef.current = unsubscribe
      if (started.status === 'failed') {
        const message = started.error || t.errorPublish('failed')
        setError(message)
        unsubscribe?.()
        publishWatchRef.current = undefined
        unsubscribe = undefined
        return
      }
      if (started.status === 'done') {
        unsubscribe?.()
        publishWatchRef.current = undefined
        unsubscribe = undefined
        setStatusLine(started.product_url ? t.publishedStatus : t.publishedNoUrl)
        return
      }
      setStatusLine(t.publishingStatus)
    } catch (err) {
      if (err instanceof GoogleAuthCancelledError) {
        setStatusLine('')
        setError(t.signInCancelled)
        toast.warning(t.signInCancelled)
      } else {
        const message = explainFailure('publish', err)
        setError(message)
        if (publishRequested) {
          try {
            const jobs = await client.listJobs()
            const latest = jobs
              .filter((item) => item.type === 'upload' && item.source_job_id === sourceId)
              .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
              .find((item) => item.id !== previousUploadId)
            if (latest) {
              announceRunSubmitted(latest.id, latest.number)
              trackRun({
                id: latest.id,
                kind: 'upload',
                status: latest.status,
                error: latest.error,
                number: latest.number,
              })
            } else {
              toast.bad(message)
            }
          } catch {
            toast.bad(message)
          }
        } else {
          toast.bad(message)
        }
        if (!unsubscribe) {
          setStatusLine('')
        }
      }
    } finally {
      setPublishing(false)
    }
  }

  async function reprocessAlbum(options?: ReprocessOptions) {
    if (!job) {
      return
    }
    const sourceId = job.id
    setReprocessing(true)
    setError(null)
    try {
      const next = await client.reprocessJob(sourceId, options)
      announceRunSubmitted(next.id, next.number)
      trackRun({
        id: next.id,
        kind: 'preview',
        status: next.status,
        error: next.error,
        number: next.number,
      })
      applyJob(next)
      if (options?.mode === 'new' && next.id !== sourceId) {
        if (onJobCreated) {
          onJobCreated(next.id, next.type)
        } else {
          navigate(`/albums/${next.id}`)
        }
        return
      }
      if (
        next.status === 'pending' ||
        next.status === 'running' ||
        next.status === 'waiting'
      ) {
        setPhase('working')
        setStatusLine(t.reprocessing)
      } else if (next.preview) {
        setPhase('preview')
        setStatusLine(t.previewReady)
      } else {
        setPhase('failed')
        setStatusLine('')
      }
      if (next.error) {
        setError(next.error)
      }
    } catch (err) {
      setError(explainFailure('reprocess', err))
    } finally {
      setReprocessing(false)
    }
  }

  if (notFound) {
    return <NotFoundPage />
  }

  return (
    <section className={phase === 'preview' ? 'workbench workbench--preview' : 'workbench'}>
      {showFolderPick ? (
        <ImportDesk
          busy={busy}
          working={phase === 'working'}
          folderLabel={folderLabel}
          fileCount={count}
          folderInputId={folderId}
          onFolder={onFolder}
          onPreparePreview={(autoPublish) => void preparePreview(autoPublish)}
          onImportWeb={(url, headers, autoPublish) => void importFromWeb(url, headers, autoPublish)}
        />
      ) : null}

      {job || statusLine || error || phase === 'working' || uploadProgress ? (
        <div className="workbench__status-rail" aria-live="polite">
          {phase === 'working' ? (
            <LoadingSpinner label={statusLine || t.loadingAlbum} />
          ) : null}
          {job ? (
            <p className="workbench__job">
              <span className="workbench__job-label">{t.jobLabel}</span>{' '}
              <code dir="ltr">{job.id}</code>
              <span className="workbench__job-type">{jobTypeLabel(job.type)}</span>
              <span className="workbench__job-status">{jobStatusLabel(job.status)}</span>
              <Link to={`/jobs/${job.id}`} className="workbench__job-link">
                {t.viewJob}
              </Link>
              {cancelTarget ? (
                <button
                  type="button"
                  className="workbench__job-cancel"
                  disabled={cancelling}
                  onClick={() => setCancelOpen(true)}
                >
                  {cancelling ? t.cancelling : t.cancelJob}
                </button>
              ) : null}
              {job.error || job.error_code ? (
                <span className="workbench__job-error" dir="auto">
                  {jobErrorMessage(job) || job.error}
                </span>
              ) : null}
            </p>
          ) : null}
          {statusLine && phase !== 'working' ? (
            <p className="workbench__status" dir="auto">
              {statusLine}
            </p>
          ) : null}
          {uploadProgress ? (
            <div
              className="workbench__upload-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={uploadProgress.percent}
              aria-label={
                uploadProgress.phase === 'store'
                  ? t.storingFilesProgress(
                      uploadProgress.current,
                      uploadProgress.total,
                      uploadProgress.percent,
                    )
                  : t.uploadProgressLabel(
                      uploadProgress.percent,
                      formatUploadBytes(uploadProgress.loaded),
                      uploadProgress.total > 0 ? formatUploadBytes(uploadProgress.total) : '',
                    )
              }
            >
              <div className="workbench__upload-progress-track">
                <div
                  className="workbench__upload-progress-fill"
                  style={{ width: `${uploadProgress.percent}%` }}
                />
              </div>
              <span className="workbench__upload-progress-label" dir="ltr">
                {uploadProgress.phase === 'store'
                  ? t.storingFilesProgress(
                      uploadProgress.current,
                      uploadProgress.total,
                      uploadProgress.percent,
                    )
                  : t.uploadProgressLabel(
                      uploadProgress.percent,
                      formatUploadBytes(uploadProgress.loaded),
                      uploadProgress.total > 0 ? formatUploadBytes(uploadProgress.total) : '',
                    )}
              </span>
            </div>
          ) : null}
          {error ? (
            <p className="workbench__error" role="alert" dir="auto">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}

      {phase === 'preview' && job?.preview ? (
        <>
          <div className="workbench__stage">
            <h2 className="workbench__stage-title">{t.albumHeading}</h2>
            {job.preview.structure_fallback ||
            (job.warnings && job.warnings.some((w) => /not a standard Arles/i.test(w))) ? (
              <p className="workbench__structure-warning" role="status" dir="auto">
                {t.structureFallbackWarning}
              </p>
            ) : null}
            <div className="workbench__fields">
              <div className="workbench__field">
                <div className="workbench__label-row">
                  <label className="workbench__label" htmlFor={`${fieldIds}-title`}>
                    {t.titleLabel}
                  </label>
                  <ModifiedMark show={dirtyState.title} />
                </div>
                <span className="workbench__hint">
                  {t.titleHintBefore}{' '}
                  <span dir="ltr">{t.titleSelector}</span>
                  {t.titleHintAfter}
                </span>
                {dirtyState.title ? (
                  <span id={`${fieldIds}-title-mod`} className="visually-hidden">
                    {t.modifiedAria}
                  </span>
                ) : null}
                <input
                  id={`${fieldIds}-title`}
                  className="workbench__input"
                  dir="auto"
                  value={title}
                  aria-describedby={dirtyState.title ? `${fieldIds}-title-mod` : undefined}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="workbench__field">
                <div className="workbench__label-row">
                  <label className="workbench__label" htmlFor={`${fieldIds}-description`}>
                    {t.galleryDescriptionLabel}
                  </label>
                  <ModifiedMark show={dirtyState.description} />
                </div>
                <span className="workbench__hint">
                  {t.galleryDescriptionHintBefore}{' '}
                  <span dir="ltr">{t.galleryDescriptionSelector}</span>
                  {t.galleryDescriptionHintAfter}
                </span>
                {dirtyState.description ? (
                  <span id={`${fieldIds}-description-mod`} className="visually-hidden">
                    {t.modifiedAria}
                  </span>
                ) : null}
                <textarea
                  id={`${fieldIds}-description`}
                  className="workbench__textarea"
                  dir="auto"
                  rows={3}
                  value={description}
                  aria-describedby={dirtyState.description ? `${fieldIds}-description-mod` : undefined}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </div>
              <div className="journal-page">
                <p className="journal-page__kicker">{t.journalKicker}</p>
                <span className="workbench__hint">
                  {t.journalHintBefore}{' '}
                  <span dir="ltr">{t.journalHintFile}</span>
                </span>
                <div className="workbench__field">
                  <div className="workbench__label-row">
                    <label className="workbench__label" htmlFor={`${fieldIds}-journal-heading`}>
                      {t.journalHeadingLabel}
                    </label>
                    <ModifiedMark show={dirtyState.journalHeading} />
                  </div>
                  {dirtyState.journalHeading ? (
                    <span id={`${fieldIds}-journal-heading-mod`} className="visually-hidden">
                      {t.modifiedAria}
                    </span>
                  ) : null}
                  <input
                    id={`${fieldIds}-journal-heading`}
                    className="workbench__input journal-page__heading"
                    dir="auto"
                    value={journalHeading}
                    aria-describedby={
                      dirtyState.journalHeading ? `${fieldIds}-journal-heading-mod` : undefined
                    }
                    onChange={(event) => setJournalHeading(event.target.value)}
                  />
                </div>
                <div className="workbench__field">
                  <div className="workbench__label-row">
                    <label className="workbench__label" htmlFor={`${fieldIds}-journal-body`}>
                      {t.journalBodyLabel}
                    </label>
                    <ModifiedMark show={dirtyState.journalBody} />
                  </div>
                  {dirtyState.journalBody ? (
                    <span id={`${fieldIds}-journal-body-mod`} className="visually-hidden">
                      {t.modifiedAria}
                    </span>
                  ) : null}
                  <textarea
                    id={`${fieldIds}-journal-body`}
                    className="workbench__textarea workbench__textarea--journal"
                    dir="auto"
                    rows={10}
                    value={journalBody}
                    aria-describedby={
                      dirtyState.journalBody ? `${fieldIds}-journal-body-mod` : undefined
                    }
                    onChange={(event) => setJournalBody(event.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="workbench__stage">
            <h2 className="workbench__stage-title">
              {t.photosHeading}
              {job.preview.multi_index ? (
                <span className="workbench__flag" dir="ltr">{t.multiIndex}</span>
              ) : null}
            </h2>
            <span className="workbench__hint">
              {t.imageTitleHintBefore}{' '}
              <span dir="ltr">{t.imageTitleSelector}</span>
              {t.imageTitleHintAfter}
            </span>
            <ul className="preview-grid">
              {items.map((item, index) => {
                const kind = previewItemKind(item)
                const thumbUrl =
                  kind === 'video'
                    ? item.thumb_relpath
                      ? client.mediaUrl(job.id, item.id, 'thumb')
                      : ''
                    : client.mediaUrl(job.id, item.id, 'thumb')
                return (
                <PreviewCard
                  key={item.id}
                  index={index + 1}
                  item={item}
                  thumbUrl={thumbUrl}
                  caption={captions[item.id] ?? item.caption}
                  captionModified={Boolean(dirtyState.captions[item.id])}
                  showDateMismatch={inferImportOrigin(job) === 'folder'}
                  onCaption={(value) => setCaptions((prev) => ({ ...prev, [item.id]: value }))}
                  onOpenPreview={() => {
                    const playable = kind !== 'video' || videoHasBrowserPlayableCopy(item)
                    setPreviewTarget({
                      id: item.id,
                      index: index + 1,
                      src:
                        kind === 'video'
                          ? playable
                            ? client.mediaUrl(job.id, item.id, 'play')
                            : ''
                          : client.mediaUrl(job.id, item.id, 'original'),
                      caption: captions[item.id] ?? item.caption,
                      kind,
                      relpath: item.relpath,
                      playable: kind === 'video' ? playable : undefined,
                      poster: item.thumb_relpath
                        ? client.mediaUrl(job.id, item.id, 'thumb')
                        : kind === 'video'
                          ? null
                          : client.mediaUrl(job.id, item.id, 'thumb'),
                    })
                  }}
                />
                )
              })}
            </ul>
          </div>

          <div className="workbench__dock">
            <div className="workbench__dock-meta">
              {photosUrl ? (
                <p className="workbench__summary">
                  <a className="workbench__link" href={photosUrl} target="_blank" rel="noreferrer">
                    {t.openPhotosAlbum}
                  </a>
                </p>
              ) : null}
            </div>
            <div className="workbench__actions">
              <button
                type="button"
                className={
                  dirty
                    ? 'workbench__button workbench__button--secondary workbench__button--save-dirty'
                    : 'workbench__button workbench__button--secondary'
                }
                disabled={busy || !dirty}
                onClick={() => void saveEdits()}
              >
                {saving ? t.saving : t.save}
              </button>
              <button
                type="button"
                className="workbench__button workbench__button--secondary"
                disabled={busy}
                onClick={() => setReprocessOpen(true)}
              >
                {reprocessing ? t.reprocessing : t.reprocess}
              </button>
              <button
                type="button"
                className="workbench__button"
                disabled={busy || publishInProgress || job.status === 'running'}
                onClick={() => void publishAlbum()}
              >
                {publishInProgress
                  ? t.alreadyRunning
                  : published
                    ? t.reupload
                    : t.publish}
              </button>
            </div>
          </div>
        </>
      ) : null}
      <ImagePreviewModal target={previewTarget} onClose={() => setPreviewTarget(null)} />
      <CancelJobDialog
        open={cancelOpen}
        jobId={cancelTarget?.id ?? null}
        onCancel={() => setCancelOpen(false)}
        onConfirm={() => void cancelActiveRun()}
      />
      {reprocessConflict ? (
        <ReprocessConflictDialog
          open={reprocessOpen}
          web={Boolean(job && inferImportOrigin(job) === 'web')}
          unsaved={dirty}
          saved={Boolean(job?.user_edited)}
          onCancel={() => setReprocessOpen(false)}
          onOverwrite={() => {
            setReprocessOpen(false)
            void reprocessAlbum({ mode: 'overwrite' })
          }}
          onCreateNew={(prefix) => {
            setReprocessOpen(false)
            void reprocessAlbum({ mode: 'new', titlePrefix: prefix })
          }}
        />
      ) : (
        <ConfirmDialog
          open={reprocessOpen}
          message={
            job && inferImportOrigin(job) === 'web' ? t.confirmReprocessWeb : t.confirmReprocess
          }
          cancelLabel={t.confirmCancel}
          confirmLabel={t.reprocess}
          danger
          onCancel={() => setReprocessOpen(false)}
          onConfirm={() => {
            setReprocessOpen(false)
            void reprocessAlbum()
          }}
        />
      )}
      <ConfirmDialog
        open={existingAlbum !== null}
        title={existingAlbum ? t.confirmOverwriteAlbumTitle(existingAlbum.title) : undefined}
        message={t.confirmOverwriteAlbumBody}
        cancelLabel={t.confirmCancel}
        confirmLabel={t.confirmOverwriteAlbumYes}
        extra={
          existingAlbum ? (
            <Link to={`/albums/${existingAlbum.id}`} className="confirm-dialog__link">
              {t.openExistingAlbum}
            </Link>
          ) : null
        }
        danger
        onCancel={() => setExistingAlbum(null)}
        onConfirm={() => void confirmOverwrite()}
      />
      <ConfirmDialog
        open={blocker.state === 'blocked'}
        message={t.discardChanges}
        cancelLabel={t.discardStay}
        confirmLabel={t.discardLeave}
        danger
        onCancel={() => {
          if (blocker.state === 'blocked') {
            blocker.reset()
          }
        }}
        onConfirm={() => {
          if (blocker.state === 'blocked') {
            blocker.proceed()
          }
        }}
      />
    </section>
  )
}
