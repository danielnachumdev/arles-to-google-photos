import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './ImagePreviewModal.css'
import { t } from '../lib/language.ts'
import { previewDescriptionLabel, previewItemKind } from '../lib/previewMedia.ts'

export type ImagePreviewTarget = {
  id: string
  index: number
  src: string
  caption?: string | null
  kind?: string | null
  relpath?: string | null
  poster?: string | null
  /** When false, skip the player and explain that no browser copy exists. */
  playable?: boolean
}

function previewCaption(target: ImagePreviewTarget): string {
  return target.caption?.trim() ?? ''
}

export function ImagePreviewModal({
  target,
  onClose,
}: {
  target: ImagePreviewTarget | null
  onClose: () => void
}) {
  const titleId = useId()
  const captionId = useId()
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const [playFailed, setPlayFailed] = useState(false)

  useEffect(() => {
    if (!target) {
      return
    }
    setPlayFailed(false)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      opener?.focus()
    }
  }, [target])

  if (!target) {
    return null
  }

  const caption = previewCaption(target)
  const descriptionLabel = previewDescriptionLabel(target, t)
  const isVideo = previewItemKind(target) === 'video'
  const hasPlayableSrc = target.playable !== false && Boolean(target.src.trim())
  const showNoBrowserCopy = isVideo && !hasPlayableSrc
  const showLoadFailed = isVideo && hasPlayableSrc && playFailed
  const statusMessage = showNoBrowserCopy
    ? t.videoPreviewNoBrowserCopy
    : showLoadFailed
      ? t.videoPreviewLoadFailed
      : null

  return createPortal(
    <div
      className="image-preview-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={caption ? captionId : undefined}
    >
      <div className="image-preview-modal__bar">
        <button
          ref={closeRef}
          type="button"
          className="image-preview-modal__close"
          onClick={onClose}
        >
          {t.close}
        </button>
        <p id={titleId} className="image-preview-modal__title">
          <span dir="ltr">{target.id}</span>
          <span className="image-preview-modal__index" dir="ltr">
            #{target.index}
          </span>
        </p>
      </div>
      <div
        className="image-preview-modal__stage"
        onClick={onClose}
      >
        {isVideo && hasPlayableSrc ? (
          <video
            className="image-preview-modal__video"
            controls
            src={target.src}
            poster={target.poster || undefined}
            aria-label={t.videoPreviewAria(target.id)}
            onClick={(event) => event.stopPropagation()}
            onError={() => setPlayFailed(true)}
          />
        ) : isVideo ? (
          <div
            className="image-preview-modal__video-fallback"
            role="img"
            aria-label={t.videoPreviewAria(target.id)}
            onClick={(event) => event.stopPropagation()}
          >
            {target.poster ? (
              <img
                className="image-preview-modal__video-poster"
                src={target.poster}
                alt=""
              />
            ) : null}
          </div>
        ) : (
          <img
            className="image-preview-modal__image"
            src={target.src}
            alt={caption || target.id}
            onClick={(event) => event.stopPropagation()}
          />
        )}
      </div>
      {statusMessage ? (
        <p className="image-preview-modal__error" role="status" dir="auto">
          {statusMessage}
        </p>
      ) : null}
      {caption ? (
        <div
          id={captionId}
          className="image-preview-modal__footer"
          dir="auto"
          onClick={(event) => event.stopPropagation()}
        >
          <p className="image-preview-modal__caption-kicker">{descriptionLabel}</p>
          <p className="image-preview-modal__caption" dir="auto">
            {caption}
          </p>
        </div>
      ) : null}
    </div>,
    document.body,
  )
}
