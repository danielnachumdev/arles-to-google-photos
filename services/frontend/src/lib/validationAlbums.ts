import type {
  ValidationMatchedAlbum,
  ValidationReport,
  ValidationSideAlbum,
} from '../api/types.ts'

export type ValidationAlbumKind = 'matched' | 'only_remote' | 'only_photos'

export type ValidationAlbumFilter =
  | 'all'
  | 'issues'
  | 'matched'
  | 'only_remote'
  | 'only_photos'

export type ValidationAlbumEntry = {
  key: string
  kind: ValidationAlbumKind
  titleId: string
  title: string
  hasIssues: boolean
  issueCount: number
  itemCount: number | null
  matched: ValidationMatchedAlbum | null
  side: ValidationSideAlbum | null
}

export function matchedIssueCount(album: ValidationMatchedAlbum): number {
  return (
    (album.only_remote_items?.length ?? 0) +
    (album.only_photos_items?.length ?? 0) +
    (album.mismatches?.length ?? 0)
  )
}

export function buildValidationAlbumEntries(
  report: ValidationReport,
): ValidationAlbumEntry[] {
  const matched = (report.matched ?? []).map((album) => {
    const issueCount = matchedIssueCount(album)
    return {
      key: `matched:${album.title_id}`,
      kind: 'matched' as const,
      titleId: album.title_id,
      title: (album.title || album.title_id).trim() || album.title_id,
      hasIssues: !album.identical,
      issueCount,
      itemCount: null,
      matched: album,
      side: null,
    }
  })
  const onlyRemote = (report.only_remote ?? []).map((album) => ({
    key: `only_remote:${album.title_id}`,
    kind: 'only_remote' as const,
    titleId: album.title_id,
    title: (album.title || album.title_id).trim() || album.title_id,
    hasIssues: true,
    issueCount: album.item_count || 0,
    itemCount: album.item_count ?? null,
    matched: null,
    side: album,
  }))
  const onlyPhotos = (report.only_photos ?? []).map((album) => ({
    key: `only_photos:${album.title_id}`,
    kind: 'only_photos' as const,
    titleId: album.title_id,
    title: (album.title || album.title_id).trim() || album.title_id,
    hasIssues: true,
    issueCount: album.item_count || 0,
    itemCount: album.item_count ?? null,
    matched: null,
    side: album,
  }))
  return [...matched, ...onlyRemote, ...onlyPhotos]
}

export function filterValidationAlbums(
  entries: readonly ValidationAlbumEntry[],
  filter: ValidationAlbumFilter,
  query: string,
): ValidationAlbumEntry[] {
  const needle = query.trim().toLowerCase()
  return entries.filter((entry) => {
    if (filter === 'issues' && !entry.hasIssues) {
      return false
    }
    if (filter === 'matched' && entry.kind !== 'matched') {
      return false
    }
    if (filter === 'only_remote' && entry.kind !== 'only_remote') {
      return false
    }
    if (filter === 'only_photos' && entry.kind !== 'only_photos') {
      return false
    }
    if (!needle) {
      return true
    }
    return (
      entry.title.toLowerCase().includes(needle) ||
      entry.titleId.toLowerCase().includes(needle)
    )
  })
}

export function defaultValidationAlbumKey(
  entries: readonly ValidationAlbumEntry[],
): string | null {
  const firstIssue = entries.find((entry) => entry.hasIssues)
  return (firstIssue ?? entries[0])?.key ?? null
}

export function formatValidationValue(value: unknown): string {
  if (value == null || value === '') {
    return '—'
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return formatByteSize(value)
  }
  if (typeof value === 'string') {
    const asNumber = Number(value)
    if (value.trim() !== '' && Number.isFinite(asNumber) && /^-?\d+(\.\d+)?$/.test(value.trim())) {
      return formatByteSize(asNumber)
    }
    return value
  }
  return String(value)
}

function formatByteSize(size: number): string {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
