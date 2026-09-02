import { type ReactNode, useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import './ConfirmDialog.css'

/** In-app confirm for operator decisions. Never use window.confirm / alert / prompt. */
export function ConfirmDialog({
  open,
  title,
  message,
  cancelLabel,
  confirmLabel,
  extra,
  onCancel,
  onConfirm,
  danger = false,
}: {
  open: boolean
  title?: string
  message?: ReactNode
  cancelLabel: string
  confirmLabel: string
  extra?: ReactNode
  onCancel: () => void
  onConfirm: () => void
  danger?: boolean
}) {
  const titleId = useId()
  const messageId = useId()
  const cancelRef = useRef<HTMLButtonElement>(null)
  const onCancelRef = useRef(onCancel)
  onCancelRef.current = onCancel

  useEffect(() => {
    if (!open) {
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    cancelRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancelRef.current()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      opener?.focus()
    }
  }, [open])

  if (!open) {
    return null
  }

  const hasMessage = message != null && message !== false && message !== ''
  const labelledBy = title ? titleId : messageId
  const describedBy = title && hasMessage ? messageId : undefined

  return createPortal(
    <div
      className="confirm-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
    >
      <button
        type="button"
        className="confirm-dialog__backdrop"
        tabIndex={-1}
        aria-hidden="true"
        onClick={onCancel}
      />
      <div className="confirm-dialog__card">
        {title ? (
          <h2 id={titleId} className="confirm-dialog__title">
            {title}
          </h2>
        ) : null}
        {hasMessage ? (
          <div
            id={messageId}
            className="confirm-dialog__message"
          >
            {typeof message === 'string' || typeof message === 'number' ? (
              <p>{message}</p>
            ) : (
              message
            )}
          </div>
        ) : null}
        <div className="confirm-dialog__actions">
          <button
            ref={cancelRef}
            type="button"
            className="confirm-dialog__cancel"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          {extra ? <div className="confirm-dialog__extra">{extra}</div> : null}
          <button
            type="button"
            className={
              danger
                ? 'confirm-dialog__confirm confirm-dialog__confirm--danger'
                : 'confirm-dialog__confirm'
            }
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
