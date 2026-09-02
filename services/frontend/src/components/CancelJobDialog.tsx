import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MigrationClient } from '../api/client.ts'
import type { JobChild } from '../api/types.ts'
import { childDisplayLabel } from '../lib/jobFields.ts'
import { jobTypeLabel, t } from '../lib/language.ts'
import { ConfirmDialog } from './ConfirmDialog.tsx'

const client = new MigrationClient()

export function affectedCancelJobLabel(job: JobChild): string {
  const display = childDisplayLabel(job)
  const parts: string[] = []
  if (job.number != null) {
    parts.push(`#${job.number}`)
  }
  if (job.type) {
    parts.push(jobTypeLabel(job.type))
  }
  if (display) {
    parts.push(display)
  }
  return parts.join(' · ') || job.id
}

export function CancelJobDialog({
  open,
  jobId,
  onCancel,
  onConfirm,
}: {
  open: boolean
  jobId: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const [descendants, setDescendants] = useState<JobChild[]>([])

  useEffect(() => {
    if (!open || !jobId) {
      setDescendants([])
      return
    }
    let cancelled = false
    void client
      .getCancelPreview(jobId)
      .then((preview) => {
        if (!cancelled) {
          setDescendants(preview.descendants)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDescendants([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [open, jobId])

  return (
    <ConfirmDialog
      open={open}
      title={t.confirmCancelJobTitle}
      message={
        descendants.length > 0 ? (
          <>
            <p>{t.confirmCancelJobWithChildrenBody}</p>
            <ul className="confirm-dialog__job-list">
              {descendants.map((child) => {
                const label = affectedCancelJobLabel(child)
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
          </>
        ) : (
          t.confirmCancelJobBody
        )
      }
      cancelLabel={t.confirmCancel}
      confirmLabel={t.confirmCancelJobYes}
      danger
      onCancel={onCancel}
      onConfirm={onConfirm}
    />
  )
}
