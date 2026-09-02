import { vi } from 'vitest'
import { jsonResponse } from './http.ts'

export type TokenCallback = (response: {
  access_token?: string
  expires_in?: number
  error?: string
  error_description?: string
}) => void

export type ErrorCallback = (error: { type?: string; message?: string } | string) => void

export type GisInitOptions = {
  client_id: string
  scope: string
  callback: TokenCallback
  error_callback?: ErrorCallback
}

/** Strategy for faking Google Identity Services in unit tests. */
export abstract class GisClientStrategy {
  abstract install(): { initTokenClient: ReturnType<typeof vi.fn>; requestAccessToken: ReturnType<typeof vi.fn> }
  uninstall(): void {
    window.google = undefined
  }
}

export class ScriptedGisClient extends GisClientStrategy {
  private readonly onInit?: (opts: GisInitOptions) => void

  constructor(onInit?: (opts: GisInitOptions) => void) {
    super()
    this.onInit = onInit
  }

  static withToken(token: string, expiresIn = 3600): ScriptedGisClient {
    return new ScriptedGisClient((opts) => {
      queueMicrotask(() => opts.callback({ access_token: token, expires_in: expiresIn }))
    })
  }

  static withCallbackError(error: string, description?: string): ScriptedGisClient {
    return new ScriptedGisClient((opts) => {
      queueMicrotask(() => opts.callback({ error, error_description: description }))
    })
  }

  static withErrorCallback(error: { type?: string; message?: string } | string): ScriptedGisClient {
    return new ScriptedGisClient((opts) => {
      queueMicrotask(() => opts.error_callback?.(error))
    })
  }

  override install(): {
    initTokenClient: ReturnType<typeof vi.fn>
    requestAccessToken: ReturnType<typeof vi.fn>
  } {
    const requestAccessToken = vi.fn()
    const onInit = this.onInit
    const initTokenClient = vi.fn((opts: GisInitOptions) => {
      onInit?.(opts)
      return { requestAccessToken }
    })
    window.google = {
      accounts: {
        oauth2: { initTokenClient },
      },
    }
    return { initTokenClient, requestAccessToken }
  }
}

export const AUTH_CONFIG = {
  client_id: 'cid.apps.googleusercontent.com',
  scopes: [
    'https://www.googleapis.com/auth/photoslibrary',
    'https://www.googleapis.com/auth/photoslibrary.appendonly',
  ],
}

export function stubAuthConfigFetch(
  config: unknown = AUTH_CONFIG,
  status = 200,
): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(config, status))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
