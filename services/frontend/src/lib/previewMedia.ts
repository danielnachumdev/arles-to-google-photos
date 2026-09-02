import type { PreviewItem, PreviewItemKind } from '../api/types.ts'
import type { MessageCatalog } from './i18n/messages.ts'

const VIDEO_EXTENSIONS = new Set([
  '.mp4',
  '.mov',
  '.avi',
  '.m4v',
  '.webm',
  '.mkv',
  '.wmv',
  '.mpg',
  '.mpeg',
])

export function previewItemKind(
  item: Pick<PreviewItem, 'relpath' | 'kind'> | { relpath?: string | null; kind?: string | null },
): PreviewItemKind {
  const explicit = item.kind?.trim().toLowerCase()
  if (explicit === 'video') {
    return 'video'
  }
  if (explicit === 'image' || explicit === 'photo') {
    return 'image'
  }
  const relpath = item.relpath ?? ''
  const match = relpath.match(/(\.[^.\\/]+)$/)
  const ext = match ? match[1].toLowerCase() : ''
  return VIDEO_EXTENSIONS.has(ext) ? 'video' : 'image'
}

export function previewDescriptionLabel(
  item: Pick<PreviewItem, 'relpath' | 'kind'> | { relpath?: string | null; kind?: string | null },
  catalog: Pick<MessageCatalog, 'descriptionLabel' | 'videoDescriptionLabel'>,
): string {
  return previewItemKind(item) === 'video'
    ? catalog.videoDescriptionLabel
    : catalog.descriptionLabel
}

export function previewOpenAria(
  item: Pick<PreviewItem, 'id' | 'relpath' | 'kind'>,
  catalog: Pick<MessageCatalog, 'openPreviewAria' | 'openVideoPreviewAria'>,
): string {
  return previewItemKind(item) === 'video'
    ? catalog.openVideoPreviewAria(item.id)
    : catalog.openPreviewAria(item.id)
}
