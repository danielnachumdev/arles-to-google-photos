import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import type { JobChild, RestartMode } from '../api/types.ts'
import { jobStatusLabel, t } from '../lib/language.ts'
import { affectedCancelJobLabel } from './CancelJobDialog.tsx'
import { ConfirmDialog } from './ConfirmDialog.tsx'

const client = new MigrationClient()

export function affectedRestartJobLabel(job: JobChild): string {
  const base = affectedCancelJobLabel(job)
  if (!job.status) {
    return base
  }
  return `${base} · ${jobStatusLabel(job.status)}`
}

function ChildJobList({ jobs, muted = false }: { jobs: JobChild[]; muted?: boolean }) {
  if (jobs.length === 0) {
    return null
  }
  return (
    <ul className={muted ? 'confirm-dialog__job-list confirm-dialog__job-list--muted' : 'confirm-dialog__job-list'}>
      {jobs.map((child) => {
        const label = affectedRestartJobLabel(child)
        return (
          <li key={child.id}>
            <Link
              to={`/jobs/${child.id}`}
              className="confirm-dialog__link"
              dir="auto"
              aria-label={t.jobsOpenAria(label)}
            >
              {label}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

export function RestartJobDialog({
  open,
  jobId,
  onCancel,
  onConfirm,
}: {
  open: boolean
  jobId: string | null
  onCancel: () => void
  onConfirm: (mode: RestartMode) => void
}) {
  const [descendants, setDescendants] = useState<JobChild[]>([])
  const [done, setDone] = useState<JobChild[]>([])
  const [remaining, setRemaining] = useState<JobChild[]>([])

  useEffect(() => {
    if (!open || !jobId) {
      setDescendants([])
      setDone([])
      setRemaining([])
      return
    }
    let cancelled = false
    void client
      .getRestartPreview(jobId)
      .then((preview) => {
        if (!cancelled) {
          setDescendants(preview.descendants)
          setDone(preview.done)
          setRemaining(preview.remaining)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDescendants([])
          setDone([])
          setRemaining([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, jobId])

  const hasScrapeChildren = descendants.length > 0

  if (!hasScrapeChildren) {
    return (
      <ConfirmDialog
        open={open}
        title={t.confirmRestartJobTitle}
        message={t.confirmRestartJobBody}
        cancelLabel={t.confirmCancel}
        confirmLabel={t.confirmRestartJobYes}
        onCancel={onCancel}
        onConfirm={() => onConfirm('all')}
      />
    )
  }

  return (
    <ConfirmDialog
      open={open}
      title={t.confirmRestartJobTitle}
      message={
        <>
          <p>{t.confirmRestartJobWithChildrenBody}</p>
          {remaining.length > 0 ? (
            <>
              <p className="confirm-dialog__list-heading">{t.confirmRestartJobRemainingHeading}</p>
              <ChildJobList jobs={remaining} />
            </>
          ) : null}
          {done.length > 0 ? (
            <>
              <p className="confirm-dialog__list-heading">{t.confirmRestartJobDoneHeading}</p>
              <ChildJobList jobs={done} muted />
            </>
          ) : null}
        </>
      }
      cancelLabel={t.confirmCancel}
      confirmLabel={t.confirmRestartJobAll}
      extra={
        <button
          type="button"
          className="confirm-dialog__confirm confirm-dialog__confirm--secondary"
          disabled={remaining.length === 0}
          onClick={() => onConfirm('remaining')}
        >
          {t.confirmRestartJobRemaining}
        </button>
      }
      onCancel={onCancel}
      onConfirm={() => onConfirm('all')}
    />
  )
}
