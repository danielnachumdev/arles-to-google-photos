import type { JobFile } from '../api/types.ts'

type RelFile = File & { webkitRelativePath?: string }

function relpathOf(file: RelFile): string {
  const rel = (file.webkitRelativePath || file.name).replaceAll('\\', '/')
  const slash = rel.indexOf('/')
  if (slash === -1) {
    return rel
  }
  return rel.slice(slash + 1)
}

export function jobFilesFromDirectory(list: FileList | null): JobFile[] {
  if (!list || list.length === 0) {
    return []
  }
  return Array.from(list).map((file) => {
    const rel = file as RelFile
    return {
      relpath: relpathOf(rel),
      blob: file,
      lastModifiedMs: file.lastModified,
    }
  })
}
