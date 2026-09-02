import { isJobProcessing } from '../lib/formatJobDuration.ts'
import { jobStatusLabel } from '../lib/language.ts'
import './JobStatusBadge.css'

export function JobStatusBadge({ status }: { status: string }) {
  const processing = isJobProcessing(status)
  return (
    <span
      className={`job-list__status job-list__status--${status}`}
      aria-busy={processing || undefined}
    >
      {jobStatusLabel(status)}
    </span>
  )
}
