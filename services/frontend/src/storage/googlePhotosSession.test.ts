import { afterEach, describe, expect, it } from 'vitest'
import { MemoryKvStore, SpyKvStore } from '../testing/index.ts'
import {
  GOOGLE_PHOTOS_DEFAULT_EXPIRES_IN_SEC,
  GOOGLE_PHOTOS_SESSION_KEY,
  GOOGLE_PHOTOS_TOKEN_SKEW_MS,
  clearGooglePhotosSession,
  isGooglePhotosSessionValid,
  readGooglePhotosSession,
  readValidGooglePhotosAccessToken,
  resetGooglePhotosSessionStore,
  setGooglePhotosSessionStore,
  writeGooglePhotosSession,
} from './googlePhotosSession.ts'

describe('googlePhotosSession', () => {
  afterEach(() => {
    resetGooglePhotosSessionStore()
  })

  it('returns null when nothing is stored', () => {
    setGooglePhotosSessionStore(new MemoryKvStore())
    expect(readGooglePhotosSession()).toBeNull()
    expect(readValidGooglePhotosAccessToken()).toBeNull()
  })

  it('persists access token and expiry', () => {
    const kv = new SpyKvStore()
    setGooglePhotosSessionStore(kv)
    writeGooglePhotosSession('ya29.tok', 3600, 1_000_000)

    expect(kv.set).toHaveBeenCalledWith(
      GOOGLE_PHOTOS_SESSION_KEY,
      JSON.stringify({ access_token: 'ya29.tok', expires_at: 1_000_000 + 3600 * 1000 }),
    )
    expect(readGooglePhotosSession()).toEqual({
      accessToken: 'ya29.tok',
      expiresAt: 1_000_000 + 3600 * 1000,
    })
    expect(readValidGooglePhotosAccessToken(1_000_000)).toBe('ya29.tok')
  })

  it('defaults expires_in when missing or invalid', () => {
    const kv = new MemoryKvStore()
    setGooglePhotosSessionStore(kv)
    writeGooglePhotosSession('ya29.tok', Number.NaN, 5_000)
    expect(readGooglePhotosSession()?.expiresAt).toBe(
      5_000 + GOOGLE_PHOTOS_DEFAULT_EXPIRES_IN_SEC * 1000,
    )
  })

  it('treats a token inside the skew window as expired', () => {
    const now = 10_000_000
    setGooglePhotosSessionStore(new MemoryKvStore())
    writeGooglePhotosSession('ya29.soon', GOOGLE_PHOTOS_TOKEN_SKEW_MS / 1000, now)
    expect(readValidGooglePhotosAccessToken(now)).toBeNull()
    expect(
      isGooglePhotosSessionValid(readGooglePhotosSession(), now - GOOGLE_PHOTOS_TOKEN_SKEW_MS - 1),
    ).toBe(true)
  })

  it('returns null for an expired token', () => {
    setGooglePhotosSessionStore(new MemoryKvStore())
    writeGooglePhotosSession('ya29.old', 60, 0)
    expect(readValidGooglePhotosAccessToken(60_000)).toBeNull()
    expect(readGooglePhotosSession()?.accessToken).toBe('ya29.old')
  })

  it('ignores corrupt or incomplete stored JSON', () => {
    setGooglePhotosSessionStore(
      new MemoryKvStore({
        [GOOGLE_PHOTOS_SESSION_KEY]: '{not-json',
      }),
    )
    expect(readGooglePhotosSession()).toBeNull()

    setGooglePhotosSessionStore(
      new MemoryKvStore({
        [GOOGLE_PHOTOS_SESSION_KEY]: JSON.stringify({ access_token: 'ya29.tok' }),
      }),
    )
    expect(readGooglePhotosSession()).toBeNull()

    setGooglePhotosSessionStore(
      new MemoryKvStore({
        [GOOGLE_PHOTOS_SESSION_KEY]: JSON.stringify({ expires_at: 1 }),
      }),
    )
    expect(readGooglePhotosSession()).toBeNull()
  })

  it('clears the stored session', () => {
    const kv = new SpyKvStore()
    setGooglePhotosSessionStore(kv)
    writeGooglePhotosSession('ya29.tok', 3600, 1)
    clearGooglePhotosSession()
    expect(kv.set).toHaveBeenCalledWith(GOOGLE_PHOTOS_SESSION_KEY, '')
    expect(readGooglePhotosSession()).toBeNull()
    expect(readValidGooglePhotosAccessToken()).toBeNull()
  })
})
