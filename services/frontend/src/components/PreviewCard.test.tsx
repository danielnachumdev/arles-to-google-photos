import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PreviewItem } from '../api/types.ts'
import { t } from '../lib/language.ts'
import { PreviewItemBuilder } from '../testing/index.ts'
import { PreviewCard } from './PreviewCard.tsx'

const ITEM: PreviewItem = PreviewItemBuilder.jpeg().build()

describe('PreviewCard', () => {
  it('opens the lightbox from the photo button, not the image title field', () => {
    const onOpenPreview = vi.fn()
    const onCaption = vi.fn()
    render(
      <ul>
        <PreviewCard
          index={1}
          item={ITEM}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={ITEM.caption}
          onCaption={onCaption}
          onOpenPreview={onOpenPreview}
        />
      </ul>,
    )

    const thumb = screen.getByRole('button', { name: t.openPreviewAria(ITEM.id) })
    expect(thumb.tagName).toBe('BUTTON')
    expect(thumb).toHaveAttribute('type', 'button')
    fireEvent.click(thumb)
    expect(onOpenPreview).toHaveBeenCalledTimes(1)

    const description = screen.getByRole('textbox', { name: t.descriptionLabel })
    expect(description.tagName).toBe('TEXTAREA')
    fireEvent.change(description, { target: { value: 'עודכן' } })
    expect(onCaption).toHaveBeenCalledWith('עודכן')
    expect(onOpenPreview).toHaveBeenCalledTimes(1)
  })

  it('shows a long back-of-photo note in full, not a one-line clip', () => {
    const longCaption =
      'בארל אחרי הצהריים ליד הנהר. הלכנו לאורך הגשר הישן ואז ישבנו בבית הקפה ליד הכיכר. השמש ירדה לאט והצלמים עמדו על המדרגות עם המצלמות. זה היה יום ארוך ומלא אור, והתיאור הזה צריך להישאר קריא במלואו על הכרטיס.'

    render(
      <ul>
        <PreviewCard
          index={1}
          item={{ ...ITEM, caption: longCaption }}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={longCaption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    const description = screen.getByLabelText(t.descriptionLabel)
    expect(description.tagName).toBe('TEXTAREA')
    expect(description).toHaveValue(longCaption)
    expect(description).toHaveAccessibleName(t.descriptionLabel)
  })

  it('keeps an empty image title note compact', () => {
    render(
      <ul>
        <PreviewCard
          index={1}
          item={{ ...ITEM, caption: '' }}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption=""
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    const description = screen.getByLabelText(t.descriptionLabel)
    expect(description.tagName).toBe('TEXTAREA')
    expect(description).toHaveValue('')
    expect(description).toHaveAttribute('rows', '2')
  })

  it('shows taken_on/mtime mismatch warning for local folder albums', () => {
    const mismatched: PreviewItem = {
      ...ITEM,
      last_modified: '2024-03-01T10:00:00',
      taken_on: '2012-08-02',
    }
    const { container } = render(
      <ul>
        <PreviewCard
          index={1}
          item={mismatched}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={mismatched.caption}
          showDateMismatch
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(container.querySelector('.preview-card__meta--differ')).toBeTruthy()
    expect(container.querySelector('.preview-card__note')?.textContent).toBe(
      `${t.dateMismatchBefore}${t.fieldTakenOn}${t.dateMismatchJoin}${t.fieldMtime}${t.dateMismatchAfter}`,
    )
    expect(screen.getByText('2012-08-02')).toBeInTheDocument()
    expect(screen.getByText('2024-03-01T10:00:00')).toBeInTheDocument()
  })

  it('hides taken_on/mtime mismatch warning for web-imported albums', () => {
    const mismatched: PreviewItem = {
      ...ITEM,
      last_modified: '2024-03-01T10:00:00',
      taken_on: '2012-08-02',
    }
    const { container } = render(
      <ul>
        <PreviewCard
          index={1}
          item={mismatched}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={mismatched.caption}
          showDateMismatch={false}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(container.querySelector('.preview-card__meta--differ')).toBeNull()
    expect(container.querySelector('.preview-card__note')).toBeNull()
    expect(screen.getByText('2012-08-02')).toBeInTheDocument()
    expect(screen.getByText('2024-03-01T10:00:00')).toBeInTheDocument()
  })

  it('shows a subtle modified mark when the caption differs from the saved preview', () => {
    render(
      <ul>
        <PreviewCard
          index={1}
          item={ITEM}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption="כיתוב חדש"
          captionModified
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(screen.getByText(t.modified)).toBeInTheDocument()
    expect(screen.getByLabelText(t.descriptionLabel)).toHaveAccessibleDescription(t.modifiedAria)
  })

  it('keeps JPEG cards on image title and preview aria', () => {
    render(
      <ul>
        <PreviewCard
          index={1}
          item={ITEM}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={ITEM.caption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(screen.getByRole('button', { name: t.openPreviewAria(ITEM.id) })).toBeInTheDocument()
    expect(screen.getByLabelText(t.descriptionLabel)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.videoDescriptionLabel)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: t.openVideoPreviewAria(ITEM.id) })).not.toBeInTheDocument()
  })

  it('uses video title and preview aria for video relpath or kind', () => {
    const videoByPath: PreviewItem = {
      ...ITEM,
      id: 'clip01',
      relpath: 'hrimages/clip01hr.wmv',
      caption: 'סרטון',
    }
    const { rerender } = render(
      <ul>
        <PreviewCard
          index={1}
          item={videoByPath}
          thumbUrl="/api/jobs/job-1/media/clip01"
          caption={videoByPath.caption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(screen.getByRole('button', { name: t.openVideoPreviewAria(videoByPath.id) })).toBeInTheDocument()
    expect(screen.getByLabelText(t.videoDescriptionLabel)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.descriptionLabel)).not.toBeInTheDocument()

    rerender(
      <ul>
        <PreviewCard
          index={2}
          item={{ ...ITEM, kind: 'video', relpath: 'hrimages/clip01hr.JPG' }}
          thumbUrl="/api/jobs/job-1/media/20120802_01"
          caption={ITEM.caption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(screen.getByRole('button', { name: t.openVideoPreviewAria(ITEM.id) })).toBeInTheDocument()
    expect(screen.getByLabelText(t.videoDescriptionLabel)).toBeInTheDocument()
    expect(screen.queryByLabelText(t.descriptionLabel)).not.toBeInTheDocument()
  })

  it('uses the thumb URL for video cards and never points the img at the wmv', () => {
    const videoItem: PreviewItem = {
      ...ITEM,
      id: '0512_1_06[1]',
      relpath: 'hrimages/0512_1_06[1]hr.wmv',
      kind: 'video',
      thumb_relpath: 'thumbnails/TN_0512_1_06[1].jpg',
    }
    const thumbUrl = '/api/jobs/job-1/media/0512_1_06%5B1%5D?variant=thumb'
    const { container } = render(
      <ul>
        <PreviewCard
          index={1}
          item={videoItem}
          thumbUrl={thumbUrl}
          caption={videoItem.caption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    const image = container.querySelector('img.preview-card__thumb')
    expect(image).toHaveAttribute('src', thumbUrl)
    expect(image?.getAttribute('src')).not.toContain('.wmv')
    expect(image?.getAttribute('src')).not.toMatch(/\/media\/[^?]+\s*$/)
    expect(container.querySelector('.preview-card__video-badge')?.textContent).toBe(t.videoBadge)
    expect(container.querySelector('.preview-card__video-placeholder')).toBeNull()
  })

  it('shows a video placeholder when no still thumb is available', () => {
    const videoItem: PreviewItem = {
      ...ITEM,
      id: 'clip01',
      relpath: 'hrimages/clip01hr.wmv',
      kind: 'video',
    }
    const { container } = render(
      <ul>
        <PreviewCard
          index={1}
          item={videoItem}
          thumbUrl=""
          caption=""
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    expect(container.querySelector('img.preview-card__thumb')).toBeNull()
    expect(container.querySelector('.preview-card__video-placeholder')).toBeTruthy()
    expect(container.querySelector('.preview-card__thumb-spinner')).toBeNull()
    expect(container.querySelector('.preview-card__video-badge')?.textContent).toBe(t.videoBadge)
  })

  it('shows a spinner until the thumbnail image finishes loading', () => {
    const { container } = render(
      <ul>
        <PreviewCard
          index={1}
          item={ITEM}
          thumbUrl="/api/jobs/job-1/media/20120802_01?variant=thumb"
          caption={ITEM.caption}
          onCaption={() => undefined}
          onOpenPreview={() => undefined}
        />
      </ul>,
    )

    const wrap = container.querySelector('.preview-card__thumb-wrap')
    const image = container.querySelector('img.preview-card__thumb')
    expect(wrap).toHaveAttribute('aria-busy', 'true')
    expect(container.querySelector('.preview-card__thumb-spinner')).toBeTruthy()
    expect(screen.getByText(t.loadingThumbnail)).toBeInTheDocument()
    expect(image).not.toHaveClass('preview-card__thumb--ready')

    fireEvent.load(image!)

    expect(wrap).not.toHaveAttribute('aria-busy')
    expect(container.querySelector('.preview-card__thumb-spinner')).toBeNull()
    expect(image).toHaveClass('preview-card__thumb--ready')
  })
})
