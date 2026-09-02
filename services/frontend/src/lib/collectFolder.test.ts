import { describe, expect, it } from 'vitest'
import { FakeAlbumFiles } from '../testing/index.ts'
import { jobFilesFromDirectory } from './collectFolder.ts'

describe('jobFilesFromDirectory', () => {
  it('strips the selected folder prefix from webkitRelativePath', () => {
    const files = jobFilesFromDirectory(
      FakeAlbumFiles.list(
        FakeAlbumFiles.file('index.html', 'Day1/index.html'),
        FakeAlbumFiles.file('a.jpg', 'Day1/hrimages/a.jpg'),
      ),
    )
    expect(files.map((f) => f.relpath)).toEqual(['index.html', 'hrimages/a.jpg'])
    expect(files[0]?.lastModifiedMs).toBe(1_343_901_600_000)
  })

  it('returns an empty list for null or empty input', () => {
    expect(jobFilesFromDirectory(null)).toEqual([])
    expect(jobFilesFromDirectory(FakeAlbumFiles.list())).toEqual([])
  })

  it('keeps a bare filename when there is no folder prefix', () => {
    const files = jobFilesFromDirectory(
      FakeAlbumFiles.list(FakeAlbumFiles.file('index.html', 'index.html')),
    )
    expect(files.map((f) => f.relpath)).toEqual(['index.html'])
  })

  it('normalizes backslashes before stripping the folder prefix', () => {
    const files = jobFilesFromDirectory(
      FakeAlbumFiles.list(FakeAlbumFiles.file('a.jpg', 'Day1\\hrimages\\a.jpg')),
    )
    expect(files.map((f) => f.relpath)).toEqual(['hrimages/a.jpg'])
  })
})
