/** Client-side album size classification (mirrors backend thresholds). */

export const LARGE_ANY_FILE_BYTES = 256 * 1024 * 1024
export const LARGE_TOTAL_BYTES = 1024 * 1024 * 1024
export const HARD_FILE_CEILING_BYTES = Math.floor(1.5 * 1024 * 1024 * 1024)

export type SizeClass = 'small' | 'large'

export type AlbumSizeStats = {
  totalBytes: number
  maxBytes: number
  sizeClass: SizeClass
  exceedsHardCeiling: boolean
}

export function albumSizeStats(
  files: ReadonlyArray<{ blob: Blob; relpath?: string }>,
): AlbumSizeStats {
  let totalBytes = 0
  let maxBytes = 0
  for (const file of files) {
    const size = Number(file.blob?.size) || 0
    // Structure HTML/CSS is tiny; still counts toward total.
    totalBytes += size
    if (size > maxBytes) {
      maxBytes = size
    }
  }
  const sizeClass: SizeClass =
    maxBytes > LARGE_ANY_FILE_BYTES || totalBytes > LARGE_TOTAL_BYTES
      ? 'large'
      : 'small'
  return {
    totalBytes,
    maxBytes,
    sizeClass,
    exceedsHardCeiling: maxBytes > HARD_FILE_CEILING_BYTES,
  }
}
