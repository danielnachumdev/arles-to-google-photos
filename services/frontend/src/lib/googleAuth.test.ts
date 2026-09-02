import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_CONFIG,
  MemoryKvStore,
  ScriptedGisClient,
  stubAuthConfigFetch,
} from '../testing/index.ts'
import {
  GOOGLE_PHOTOS_SESSION_KEY,
  readValidGooglePhotosAccessToken,
  resetGooglePhotosSessionStore,
  setGooglePhotosSessionStore,
  writeGooglePhotosSession,
} from '../storage/googlePhotosSession.ts'
import {
  fetchGoogleAuthConfig,
  GOOGLE_AUTH_POPUP_DISMISS_MS,
  GoogleAuthCancelledError,
  isGoogleUnauthorizedError,
  requestGooglePhotosAccessToken,
} from './googleAuth.ts'
import { withGooglePhotosAccessToken } from './withGooglePhotosToken.ts'

describe('googleAuth', () => {
  beforeEach(() => {
    setGooglePhotosSessionStore(new MemoryKvStore())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    window.google = undefined
    resetGooglePhotosSessionStore()
    document.querySelectorAll('script[src="https://accounts.google.com/gsi/client"]').forEach((node) => {
      node.remove()
    })
  })

  it('loads client id and scopes from /api/auth/config', async () => {
    const fetchMock = stubAuthConfigFetch()

    await expect(fetchGoogleAuthConfig()).resolves.toEqual(AUTH_CONFIG)
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/config')
  })

  it('rejects when auth config is missing or incomplete', async () => {
    stubAuthConfigFetch({ detail: 'not configured' }, 503)
    await expect(fetchGoogleAuthConfig()).rejects.toThrow(/503/)

    stubAuthConfigFetch({ client_id: '', scopes: [] })
    await expect(fetchGoogleAuthConfig()).rejects.toThrow(/not configured/i)
  })

  it('requests a Google Photos access token via GIS', async () => {
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.tok').install()

    await expect(requestGooglePhotosAccessToken()).resolves.toBe('ya29.tok')
    expect(gis.initTokenClient).toHaveBeenCalledWith(
      expect.objectContaining({
        client_id: 'cid.apps.googleusercontent.com',
        scope: expect.stringContaining('photoslibrary.appendonly'),
      }),
    )
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: '' })
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.tok')
  })

  it('reuses a still-valid stored token without calling GIS', async () => {
    writeGooglePhotosSession('ya29.cached', 3600)
    const fetchMock = stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.gis').install()

    await expect(requestGooglePhotosAccessToken()).resolves.toBe('ya29.cached')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(gis.initTokenClient).not.toHaveBeenCalled()
    expect(gis.requestAccessToken).not.toHaveBeenCalled()
  })

  it('requests GIS and persists when the stored token is expired', async () => {
    writeGooglePhotosSession('ya29.old', 60, 0)
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.fresh').install()

    await expect(requestGooglePhotosAccessToken()).resolves.toBe('ya29.fresh')
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: '' })
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.fresh')
  })

  it('requests GIS when no token is stored', async () => {
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.new').install()

    await expect(requestGooglePhotosAccessToken()).resolves.toBe('ya29.new')
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: '' })
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.new')
  })

  it('force-refreshes with an interactive GIS prompt', async () => {
    writeGooglePhotosSession('ya29.cached', 3600)
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.forced').install()

    await expect(requestGooglePhotosAccessToken({ force: true })).resolves.toBe('ya29.forced')
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: 'consent' })
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.forced')
  })

  it('retries an action after GIS when it fails with HTTP 401', async () => {
    writeGooglePhotosSession('ya29.old', 3600)
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.new').install()
    const action = vi
      .fn()
      .mockRejectedValueOnce(new Error('HTTP 401: {"detail":"invalid token"}'))
      .mockResolvedValueOnce({ id: 'upload-1' })

    await expect(withGooglePhotosAccessToken(action)).resolves.toEqual({ id: 'upload-1' })
    expect(action).toHaveBeenNthCalledWith(1, 'ya29.old')
    expect(action).toHaveBeenNthCalledWith(2, 'ya29.new')
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: 'consent' })
    expect(readValidGooglePhotosAccessToken()).toBe('ya29.new')
  })

  it('does not retry an action for non-401 failures', async () => {
    writeGooglePhotosSession('ya29.tok', 3600)
    const action = vi.fn().mockRejectedValueOnce(new Error('HTTP 500: {"detail":"quota"}'))

    await expect(withGooglePhotosAccessToken(action)).rejects.toThrow(/500/)
    expect(action).toHaveBeenCalledTimes(1)
    expect(action).toHaveBeenCalledWith('ya29.tok')
  })

  it('detects unauthorized publish errors', () => {
    expect(isGoogleUnauthorizedError(new Error('HTTP 401: {"detail":"invalid token"}'))).toBe(true)
    expect(isGoogleUnauthorizedError(new Error('HTTP 500: boom'))).toBe(false)
    expect(isGoogleUnauthorizedError('HTTP 401')).toBe(false)
  })

  it('detects unauthorized ApiError by code/status', async () => {
    const { ApiError } = await import('./formatApiError.ts')
    expect(isGoogleUnauthorizedError(new ApiError('unauthorized', { status: 401 }))).toBe(true)
  })

  it('ignores a corrupt stored session and requests GIS', async () => {
    setGooglePhotosSessionStore(
      new MemoryKvStore({
        [GOOGLE_PHOTOS_SESSION_KEY]: '{broken',
      }),
    )
    stubAuthConfigFetch()
    const gis = ScriptedGisClient.withToken('ya29.repaired').install()

    await expect(requestGooglePhotosAccessToken()).resolves.toBe('ya29.repaired')
    expect(gis.requestAccessToken).toHaveBeenCalledWith({ prompt: '' })
  })

  it('rejects as cancelled when GIS reports popup_closed_by_user', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withCallbackError('popup_closed_by_user').install()

    await expect(requestGooglePhotosAccessToken()).rejects.toBeInstanceOf(GoogleAuthCancelledError)
  })

  it('rejects as cancelled when GIS reports access_denied', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withCallbackError('access_denied', 'User denied access').install()

    await expect(requestGooglePhotosAccessToken()).rejects.toMatchObject({
      name: 'GoogleAuthCancelledError',
      message: 'User denied access',
    })
  })

  it('rejects as cancelled when GIS error_callback reports popup_closed', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withErrorCallback({ type: 'popup_closed' }).install()

    await expect(requestGooglePhotosAccessToken()).rejects.toBeInstanceOf(GoogleAuthCancelledError)
  })

  it('rejects with a regular Error when the popup is blocked', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withErrorCallback({
      type: 'popup_failed_to_open',
      message: 'Popup was blocked',
    }).install()

    const err = await requestGooglePhotosAccessToken().catch((caught: unknown) => caught)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(GoogleAuthCancelledError)
    expect((err as Error).message).toBe('Popup was blocked')
  })

  it('rejects with a regular Error for OAuth API failures', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withCallbackError('invalid_scope', 'Bad scope').install()

    const err = await requestGooglePhotosAccessToken().catch((caught: unknown) => caught)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(GoogleAuthCancelledError)
    expect((err as Error).message).toBe('Bad scope')
  })

  it('rejects as cancelled when the popup is closed without a GIS callback', async () => {
    stubAuthConfigFetch()
    const gis = new ScriptedGisClient().install()

    const pending = requestGooglePhotosAccessToken()
    const cancelled = expect(pending).rejects.toBeInstanceOf(GoogleAuthCancelledError)
    await vi.waitFor(() => expect(gis.requestAccessToken).toHaveBeenCalled())

    vi.useFakeTimers()
    window.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(GOOGLE_AUTH_POPUP_DISMISS_MS)
    await cancelled
  })

  it('still resolves if GIS returns a token shortly after window focus', async () => {
    stubAuthConfigFetch()
    let callback: ((response: { access_token?: string }) => void) | undefined
    const gis = new ScriptedGisClient((opts) => {
      callback = opts.callback
    }).install()

    const pending = requestGooglePhotosAccessToken()
    await vi.waitFor(() => expect(gis.requestAccessToken).toHaveBeenCalled())

    vi.useFakeTimers()
    window.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(GOOGLE_AUTH_POPUP_DISMISS_MS / 2)
    callback?.({ access_token: 'ya29.tok' })
    await vi.advanceTimersByTimeAsync(GOOGLE_AUTH_POPUP_DISMISS_MS)

    await expect(pending).resolves.toBe('ya29.tok')
  })

  it('loads the GIS script when oauth2 is not yet on window', async () => {
    stubAuthConfigFetch()
    const pending = requestGooglePhotosAccessToken()
    await vi.waitFor(() => {
      expect(document.querySelector('script[src="https://accounts.google.com/gsi/client"]')).toBeTruthy()
    })
    const script = document.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]',
    ) as HTMLScriptElement
    ScriptedGisClient.withToken('ya29.from-script').install()
    script.dispatchEvent(new Event('load'))
    await expect(pending).resolves.toBe('ya29.from-script')
  })

  it('rejects when the GIS script fails to load', async () => {
    stubAuthConfigFetch()
    const pending = requestGooglePhotosAccessToken()
    await vi.waitFor(() => {
      expect(document.querySelector('script[src="https://accounts.google.com/gsi/client"]')).toBeTruthy()
    })
    const script = document.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]',
    ) as HTMLScriptElement
    script.dispatchEvent(new Event('error'))
    await expect(pending).rejects.toThrow(/Failed to load Google sign-in/)
  })

  it('reuses a GIS script tag already in the document', async () => {
    const existing = document.createElement('script')
    existing.src = 'https://accounts.google.com/gsi/client'
    document.head.appendChild(existing)
    stubAuthConfigFetch()
    const pending = requestGooglePhotosAccessToken()
    ScriptedGisClient.withToken('ya29.existing').install()
    existing.dispatchEvent(new Event('load'))
    await expect(pending).resolves.toBe('ya29.existing')
  })

  it('rejects when an existing GIS script tag fails to load', async () => {
    const existing = document.createElement('script')
    existing.src = 'https://accounts.google.com/gsi/client'
    document.head.appendChild(existing)
    const addSpy = vi.spyOn(existing, 'addEventListener')
    stubAuthConfigFetch()
    const pending = requestGooglePhotosAccessToken()
    await vi.waitFor(() => expect(addSpy).toHaveBeenCalled())
    existing.dispatchEvent(new Event('error'))
    await expect(pending).rejects.toThrow(/Failed to load Google sign-in/)
  })

  it('treats a string error_callback as cancelled when it looks like a cancel code', async () => {
    stubAuthConfigFetch()
    ScriptedGisClient.withErrorCallback('popup_closed_by_user').install()
    await expect(requestGooglePhotosAccessToken()).rejects.toBeInstanceOf(GoogleAuthCancelledError)
  })

  it('cancels when GIS returns neither a token nor an error code', async () => {
    stubAuthConfigFetch()
    new ScriptedGisClient((opts) => {
      queueMicrotask(() => opts.callback({}))
    }).install()
    await expect(requestGooglePhotosAccessToken()).rejects.toBeInstanceOf(GoogleAuthCancelledError)
  })

  it('rejects when GIS is still unavailable after the script loads', async () => {
    stubAuthConfigFetch()
    const pending = requestGooglePhotosAccessToken()
    await vi.waitFor(() => {
      expect(document.querySelector('script[src="https://accounts.google.com/gsi/client"]')).toBeTruthy()
    })
    const script = document.querySelector(
      'script[src="https://accounts.google.com/gsi/client"]',
    ) as HTMLScriptElement
    script.dispatchEvent(new Event('load'))
    await expect(pending).rejects.toThrow(/unavailable/i)
  })
})
