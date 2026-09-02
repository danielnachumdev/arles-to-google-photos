import type { AlbumPreview } from '../api/types.ts'

export type PreviewFormValues = {
  title: string
  description: string
  journalHeading: string
  journalBody: string
  captions: Record<string, string>
}

export type PreviewDirtyFields = {
  title: boolean
  description: boolean
  journalHeading: boolean
  journalBody: boolean
  captions: Record<string, boolean>
}

export function normalizeJournalParagraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export function normalizeJournalHeading(heading: string): string | null {
  const trimmed = heading.trim()
  return trimmed ? trimmed : null
}

function paragraphsEqual(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false
  }
  return left.every((part, index) => part === right[index])
}

export function previewDirtyFields(
  preview: AlbumPreview | null | undefined,
  values: PreviewFormValues,
): PreviewDirtyFields {
  if (!preview) {
    return {
      title: false,
      description: false,
      journalHeading: false,
      journalBody: false,
      captions: {},
    }
  }

  const savedHeading = normalizeJournalHeading(preview.journal?.heading ?? '')
  const currentHeading = normalizeJournalHeading(values.journalHeading)
  const savedParagraphs = normalizeJournalParagraphs(
    (preview.journal?.paragraphs ?? []).join('\n\n'),
  )
  const currentParagraphs = normalizeJournalParagraphs(values.journalBody)

  const captions: Record<string, boolean> = {}
  for (const item of preview.items) {
    const current = values.captions[item.id] ?? item.caption
    captions[item.id] = current !== item.caption
  }

  return {
    title: values.title !== preview.title,
    description: values.description !== (preview.description ?? ''),
    journalHeading: currentHeading !== savedHeading,
    journalBody: !paragraphsEqual(currentParagraphs, savedParagraphs),
    captions,
  }
}

export function isPreviewDirty(fields: PreviewDirtyFields): boolean {
  return (
    fields.title
    || fields.description
    || fields.journalHeading
    || fields.journalBody
    || Object.values(fields.captions).some(Boolean)
  )
}

export function computePreviewDirty(
  preview: AlbumPreview | null | undefined,
  values: PreviewFormValues,
): PreviewDirtyFields & { dirty: boolean } {
  const fields = previewDirtyFields(preview, values)
  return { ...fields, dirty: isPreviewDirty(fields) }
}
