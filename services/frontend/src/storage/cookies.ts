export type CookieStore = {
  get(key: string): string | null
  set(key: string, value: string): void
  remove(key: string): void
  clear(): void
}

const YEAR_SECONDS = 60 * 60 * 24 * 365

export function createMemoryCookieStore(initial: Record<string, string> = {}): CookieStore {
  const map = new Map(Object.entries(initial))

  return {
    get(key: string): string | null {
      return map.has(key) ? map.get(key)! : null
    },
    set(key: string, value: string): void {
      map.set(key, value)
    },
    remove(key: string): void {
      map.delete(key)
    },
    clear(): void {
      map.clear()
    },
  }
}

function readDocumentCookies(): Map<string, string> {
  const map = new Map<string, string>()
  const raw = document.cookie
  if (!raw) {
    return map
  }
  for (const part of raw.split(';')) {
    const trimmed = part.trim()
    if (!trimmed) {
      continue
    }
    const eq = trimmed.indexOf('=')
    if (eq === -1) {
      continue
    }
    const name = decodeURIComponent(trimmed.slice(0, eq).trim())
    const value = decodeURIComponent(trimmed.slice(eq + 1))
    map.set(name, value)
  }
  return map
}

function writeDocumentCookie(name: string, value: string, maxAgeSeconds: number): void {
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`
}

export function createDocumentCookieStore(): CookieStore {
  return {
    get(key: string): string | null {
      try {
        return readDocumentCookies().get(key) ?? null
      } catch {
        return null
      }
    },
    set(key: string, value: string): void {
      try {
        writeDocumentCookie(key, value, YEAR_SECONDS)
      } catch {
        // private mode / cookie blocked — keep the UI running
      }
    },
    remove(key: string): void {
      try {
        writeDocumentCookie(key, '', 0)
      } catch {
        // ignore
      }
    },
    clear(): void {
      try {
        for (const key of readDocumentCookies().keys()) {
          writeDocumentCookie(key, '', 0)
        }
      } catch {
        // ignore
      }
    },
  }
}
