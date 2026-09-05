import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import type { PreviewItem } from '../api/types.ts'
import { t } from '../lib/language.ts'
import {
  previewDescriptionLabel,
  previewItemKind,
  previewOpenAria,
} from '../lib/previewMedia.ts'
import { ModifiedMark } from './ModifiedMark.tsx'
import './PreviewCard.css'
import './LoadingSpinner.css'

function syncNoteHeight(el: HTMLTextAreaElement): void {
  el.style.height = 'auto'
  const next = el.scrollHeight
  if (next > 0) {
    el.style.height = `${next}px`
  }
}

export function PreviewCard({
  index,
  item,
  thumbUrl,
  caption,
  captionModified = false,
  showDateMismatch = true,
  onCaption,
  onOpenPreview,
}: {
  index: number
  item: PreviewItem
  thumbUrl: string
  caption: string
  captionModified?: boolean
  showDateMismatch?: boolean
  onCaption: (value: string) => void
  onOpenPreview: () => void
}) {
  const captionId = useId()
  const modifiedId = useId()
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const thumbRef = useRef<HTMLImageElement>(null)
  const [thumbReady, setThumbReady] = useState(false)
  const takenDay = item.taken_on?.slice(0, 10) ?? null
  const mtimeDay = item.last_modified?.slice(0, 10) ?? null
  const datesDiffer = Boolean(
    showDateMismatch && takenDay && mtimeDay && takenDay !== mtimeDay,
  )

  useEffect(() => {
    setThumbReady(false)
  }, [thumbUrl])

  useLayoutEffect(() => {
    const el = noteRef.current
    if (el) {
      syncNoteHeight(el)
    }
  }, [caption])

  useLayoutEffect(() => {
    const img = thumbRef.current
    if (img?.complete && img.naturalWidth > 0) {
      setThumbReady(true)
    }
  }, [thumbUrl])

  const descriptionLabel = previewDescriptionLabel(item, t)
  const openPreviewAria = previewOpenAria(item, t)
  const isVideo = previewItemKind(item) === 'video'
  const thumbLoading = Boolean(thumbUrl) && !thumbReady

  return (
    <li className="preview-card">
      <div className="preview-card__sprocket">
        <span className="preview-card__hole" aria-hidden="true" />
        <span className="preview-card__hole" aria-hidden="true" />
        <span className="preview-card__index" dir="ltr">#{index}</span>
        <span className="preview-card__hole" aria-hidden="true" />
        <span className="preview-card__hole" aria-hidden="true" />
      </div>
      <button
        type="button"
        className="preview-card__thumb-btn"
        aria-haspopup="dialog"
        aria-label={openPreviewAria}
        onClick={onOpenPreview}
      >
        <span
          className="preview-card__thumb-wrap"
          aria-busy={thumbLoading || undefined}
        >
          {thumbUrl ? (
            <img
              ref={thumbRef}
              className={
                thumbReady
                  ? 'preview-card__thumb preview-card__thumb--ready'
                  : 'preview-card__thumb'
              }
              src={thumbUrl}
              alt=""
              width={160}
              loading="lazy"
              decoding="async"
              onLoad={() => setThumbReady(true)}
              onError={() => setThumbReady(true)}
            />
          ) : (
            <span className="preview-card__video-placeholder" aria-hidden="true" />
          )}
          {thumbLoading ? (
            <>
              <span className="preview-card__thumb-spinner" aria-hidden="true">
                <span className="loading-spinner__mark" />
              </span>
              <span className="visually-hidden">{t.loadingThumbnail}</span>
            </>
          ) : null}
          {isVideo ? (
            <span className="preview-card__video-badge">{t.videoBadge}</span>
          ) : null}
        </span>
      </button>
      <div className="preview-card__body">
        <div className="preview-card__id" dir="ltr">{item.id}</div>
        <dl
          className={datesDiffer ? 'preview-card__meta preview-card__meta--differ' : 'preview-card__meta'}
          dir="ltr"
        >
          <div>
            <dt>{t.fieldTakenOn}</dt>
            <dd>{item.taken_on ?? t.missingValue}</dd>
          </div>
          <div>
            <dt>{t.fieldRelpath}</dt>
            <dd>{item.relpath}</dd>
          </div>
          <div>
            <dt>{t.fieldSize}</dt>
            <dd>{item.size_bytes.toLocaleString()} {t.sizeUnit}</dd>
          </div>
          <div>
            <dt>{t.fieldMtime}</dt>
            <dd>{item.last_modified ?? t.missingValue}</dd>
          </div>
        </dl>
        {datesDiffer ? (
          <p className="preview-card__note">
            {t.dateMismatchBefore}
            <span dir="ltr">{t.fieldTakenOn}</span>
            {t.dateMismatchJoin}
            <span dir="ltr">{t.fieldMtime}</span>
            {t.dateMismatchAfter}
          </p>
        ) : null}
        <div className="preview-card__caption">
          <div className="preview-card__caption-row">
            <label className="preview-card__caption-label" htmlFor={captionId}>
              {descriptionLabel}
            </label>
            <ModifiedMark show={captionModified} />
          </div>
          {captionModified ? (
            <span id={modifiedId} className="visually-hidden">
              {t.modifiedAria}
            </span>
          ) : null}
          <textarea
            id={captionId}
            ref={noteRef}
            className="preview-card__textarea"
            dir="auto"
            rows={2}
            value={caption}
            aria-describedby={captionModified ? modifiedId : undefined}
            onChange={(event) => onCaption(event.target.value)}
          />
        </div>
      </div>
    </li>
  )
}
