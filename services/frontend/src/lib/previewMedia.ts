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

/** Formats HTML5 video can usually play without a transcoded sidecar. */
const BROWSER_PLAYABLE_VIDEO = new Set(['.mp4', '.m4v', '.webm'])

function extensionOf(relpath: string | null | undefined): string {
  const match = (relpath ?? '').match(/(\.[^.\\/]+)$/)
  return match ? match[1].toLowerCase() : ''
}

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
  return VIDEO_EXTENSIONS.has(extensionOf(item.relpath)) ? 'video' : 'image'
}

/** True when the lightbox can request a browser-decodable play URL. */
export function videoHasBrowserPlayableCopy(
  item: Pick<PreviewItem, 'relpath' | 'kind' | 'play_relpath'> | {
    relpath?: string | null
    kind?: string | null
    play_relpath?: string | null
  },
): boolean {
  if (previewItemKind(item) !== 'video') {
    return false
  }
  if (item.play_relpath?.trim()) {
    return true
  }
  return BROWSER_PLAYABLE_VIDEO.has(extensionOf(item.relpath))
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
