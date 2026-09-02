export type KeyValueStore = {
  get(key: string): string | null
  set(key: string, value: string): void
}

function resolveDefaultStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function createLocalStorageStore(storage?: Storage): KeyValueStore {
  const backing = storage ?? resolveDefaultStorage()

  return {
    get(key: string): string | null {
      try {
        return backing ? backing.getItem(key) : null
      } catch {
        return null
      }
    },
    set(key: string, value: string): void {
      try {
        backing?.setItem(key, value)
      } catch {
        // private mode / quota — keep the UI running
      }
    },
  }
}
