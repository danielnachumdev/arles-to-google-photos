import { createLocalStorageStore, type KeyValueStore } from './kv.ts'

/** localStorage key for the browser-only Google Photos GIS session. */
export const GOOGLE_PHOTOS_SESSION_KEY = 'arles.googlePhotos.session'

/** Treat a token as expired this many ms before `expires_at`. */
export const GOOGLE_PHOTOS_TOKEN_SKEW_MS = 60_000

/** GIS access tokens are typically one hour. */
export const GOOGLE_PHOTOS_DEFAULT_EXPIRES_IN_SEC = 3600

export type GooglePhotosSession = {
  accessToken: string
  expiresAt: number
}

type StoredGooglePhotosSession = {
  access_token?: unknown
  expires_at?: unknown
}

let store: KeyValueStore = createLocalStorageStore()

export function setGooglePhotosSessionStore(next: KeyValueStore): void {
  store = next
}

export function resetGooglePhotosSessionStore(): void {
  store = createLocalStorageStore()
}

function parseSession(raw: string | null): GooglePhotosSession | null {
  if (!raw) {
    return null
  }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    const record = parsed as StoredGooglePhotosSession
    if (typeof record.access_token !== 'string' || !record.access_token) {
      return null
    }
    if (typeof record.expires_at !== 'number' || !Number.isFinite(record.expires_at)) {
      return null
    }
    return { accessToken: record.access_token, expiresAt: record.expires_at }
  } catch {
    return null
  }
}

export function readGooglePhotosSession(): GooglePhotosSession | null {
  return parseSession(store.get(GOOGLE_PHOTOS_SESSION_KEY))
}

export function isGooglePhotosSessionValid(
  session: GooglePhotosSession | null,
  nowMs = Date.now(),
  skewMs = GOOGLE_PHOTOS_TOKEN_SKEW_MS,
): boolean {
  return session != null && session.expiresAt - skewMs > nowMs
}

export function readValidGooglePhotosAccessToken(nowMs = Date.now()): string | null {
  const session = readGooglePhotosSession()
  return isGooglePhotosSessionValid(session, nowMs) ? session!.accessToken : null
}

export function writeGooglePhotosSession(
  accessToken: string,
  expiresInSeconds?: number,
  nowMs = Date.now(),
): void {
  const ttlSeconds =
    typeof expiresInSeconds === 'number' && Number.isFinite(expiresInSeconds) && expiresInSeconds > 0
      ? expiresInSeconds
      : GOOGLE_PHOTOS_DEFAULT_EXPIRES_IN_SEC
  store.set(
    GOOGLE_PHOTOS_SESSION_KEY,
    JSON.stringify({
      access_token: accessToken,
      expires_at: nowMs + ttlSeconds * 1000,
    }),
  )
}

export function clearGooglePhotosSession(): void {
  store.set(GOOGLE_PHOTOS_SESSION_KEY, '')
}
