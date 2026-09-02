const DEFAULT_MTIME = 1_343_901_600_000

/** Browser folder-picker fakes for import desk / collectFolder tests. */
export class FakeAlbumFiles {
  static file(name: string, rel: string, lastModified = DEFAULT_MTIME): File {
    const file = new File([new Uint8Array([1, 2, 3])], name, { lastModified })
    Object.defineProperty(file, 'webkitRelativePath', { value: rel })
    return file
  }

  static list(...files: File[]): FileList {
    return {
      length: files.length,
      item(i: number) {
        return files[i] ?? null
      },
      *[Symbol.iterator]() {
        yield* files
      },
      ...Object.fromEntries(files.map((file, index) => [index, file])),
    } as unknown as FileList
  }

  static day1Index(lastModified = DEFAULT_MTIME): FileList {
    return FakeAlbumFiles.list(FakeAlbumFiles.file('index.html', 'Day1/index.html', lastModified))
  }

  static assignToInput(input: HTMLInputElement, files: FileList): void {
    Object.defineProperty(input, 'files', { configurable: true, value: files })
  }
}
