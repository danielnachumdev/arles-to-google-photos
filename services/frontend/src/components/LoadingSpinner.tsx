import './LoadingSpinner.css'

type LoadingSpinnerProps = {
  label: string
  className?: string
}

export function LoadingSpinner({ label, className }: LoadingSpinnerProps) {
  const classes = ['loading-spinner', className].filter(Boolean).join(' ')
  return (
    <div className={classes} role="status" aria-busy="true" aria-live="polite">
      <span className="loading-spinner__mark" aria-hidden="true" />
      <span className="loading-spinner__label">{label}</span>
    </div>
  )
}
