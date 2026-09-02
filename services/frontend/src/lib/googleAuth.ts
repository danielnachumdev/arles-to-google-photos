import {
  readValidGooglePhotosAccessToken,
  writeGooglePhotosSession,
} from '../storage/googlePhotosSession.ts'
import { apiErrorFromHttp } from './formatApiError.ts'

const GIS_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'

/** After the opener regains focus, wait this long for a GIS callback before treating the popup as dismissed. */
export const GOOGLE_AUTH_POPUP_DISMISS_MS = 800

const CANCEL_CODES = new Set([
  'popup_closed_by_user',
  'popup_closed',
  'access_denied',
])

export type GoogleAuthConfig = {
  client_id: string
  scopes: string[]
}

export type RequestGooglePhotosTokenOptions = {
  baseUrl?: string
  /** Ignore a still-valid stored token and request a new one from GIS. */
  force?: boolean
}

export class GoogleAuthCancelledError extends Error {
  constructor(message = 'Google sign-in was cancelled') {
    super(message)
    this.name = 'GoogleAuthCancelledError'
  }
}

type GoogleTokenClient = {
  requestAccessToken: (override?: { prompt?: string }) => void
}

type GoogleTokenResponse = {
  access_token?: string
  expires_in?: number
  error?: string
  error_description?: string
}

type GoogleTokenClientError = {
  type?: string
  message?: string
}

type GoogleOauth2 = {
  initTokenClient: (config: {
    client_id: string
    scope: string
    callback: (response: GoogleTokenResponse) => void
    error_callback?: (error: GoogleTokenClientError | string) => void
  }) => GoogleTokenClient
}

function googleOauth2(): GoogleOauth2 | undefined {
  return window.google?.accounts?.oauth2
}

function isCancelCode(code: string | undefined): boolean {
  return typeof code === 'string' && CANCEL_CODES.has(code.toLowerCase())
}

function tokenClientErrorParts(error: GoogleTokenClientError | string): {
  type?: string
  message: string
} {
  if (typeof error === 'string') {
    return { type: error, message: error }
  }
  const type = error.type
  return { type, message: error.message || type || 'Google sign-in was cancelled' }
}

async function loadGisClient(): Promise<GoogleOauth2> {
  const existing = googleOauth2()
  if (existing) {
    return existing
  }
  await new Promise<void>((resolve, reject) => {
    const already = document.querySelector(`script[src="${GIS_SCRIPT_SRC}"]`)
    if (already) {
      already.addEventListener('load', () => resolve(), { once: true })
      already.addEventListener('error', () => reject(new Error('Failed to load Google sign-in')), {
        once: true,
      })
      return
    }
    const script = document.createElement('script')
    script.src = GIS_SCRIPT_SRC
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google sign-in'))
    document.head.appendChild(script)
  })
  const loaded = googleOauth2()
  if (!loaded) {
    throw new Error('Google sign-in is unavailable')
  }
  return loaded
}

function normalizeTokenOptions(
  options: RequestGooglePhotosTokenOptions | string = {},
): RequestGooglePhotosTokenOptions {
  return typeof options === 'string' ? { baseUrl: options } : options
}

export function isGoogleUnauthorizedError(error: unknown): boolean {
  if (error && typeof error === 'object' && 'code' in error && (error as { code?: unknown }).code === 'unauthorized') {
    return true
  }
  if (error && typeof error === 'object' && 'status' in error && (error as { status?: unknown }).status === 401) {
    return true
  }
  return error instanceof Error && /^HTTP 401\b/.test(error.message)
}

export async function fetchGoogleAuthConfig(baseUrl = '/api'): Promise<GoogleAuthConfig> {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/auth/config`)
  if (!response.ok) {
    const body = await response.text()
    throw apiErrorFromHttp(response.status, body)
  }
  const payload = (await response.json()) as Partial<GoogleAuthConfig>
  if (!payload.client_id || !Array.isArray(payload.scopes) || payload.scopes.length === 0) {
    throw new Error('Google OAuth is not configured on the server')
  }
  return { client_id: payload.client_id, scopes: payload.scopes }
}

export async function requestGooglePhotosAccessToken(
  options: RequestGooglePhotosTokenOptions | string = {},
): Promise<string> {
  const opts = normalizeTokenOptions(options)
  const baseUrl = opts.baseUrl ?? '/api'

  if (!opts.force) {
    const stored = readValidGooglePhotosAccessToken()
    if (stored) {
      return stored
    }
  }

  const config = await fetchGoogleAuthConfig(baseUrl)
  const oauth2 = await loadGisClient()
  const prompt = opts.force ? 'consent' : ''
  return new Promise<string>((resolve, reject) => {
    let settled = false
    let dismissTimer: ReturnType<typeof setTimeout> | undefined

    const finish = (action: () => void) => {
      if (settled) {
        return
      }
      settled = true
      window.removeEventListener('focus', onWindowFocus)
      if (dismissTimer !== undefined) {
        clearTimeout(dismissTimer)
      }
      action()
    }

    const rejectCancel = (message?: string) => {
      finish(() => reject(new GoogleAuthCancelledError(message)))
    }

    const rejectFailure = (message: string) => {
      finish(() => reject(new Error(message)))
    }

    const onWindowFocus = () => {
      if (settled) {
        return
      }
      if (dismissTimer !== undefined) {
        clearTimeout(dismissTimer)
      }
      dismissTimer = setTimeout(() => {
        rejectCancel('Google sign-in was cancelled')
      }, GOOGLE_AUTH_POPUP_DISMISS_MS)
    }

    const client = oauth2.initTokenClient({
      client_id: config.client_id,
      scope: config.scopes.join(' '),
      callback: (response) => {
        if (response.error || !response.access_token) {
          const message =
            response.error_description || response.error || 'Google sign-in was cancelled'
          if (!response.error || isCancelCode(response.error)) {
            rejectCancel(message)
            return
          }
          rejectFailure(message)
          return
        }
        writeGooglePhotosSession(response.access_token, response.expires_in)
        finish(() => resolve(response.access_token as string))
      },
      error_callback: (error) => {
        const { type, message } = tokenClientErrorParts(error)
        if (!type || isCancelCode(type)) {
          rejectCancel(message)
          return
        }
        rejectFailure(message)
      },
    })

    window.addEventListener('focus', onWindowFocus)
    client.requestAccessToken({ prompt })
  })
}

declare global {
  interface Window {
    google?: {
      accounts?: {
        oauth2?: GoogleOauth2
      }
    }
  }
}
