import { clearGooglePhotosSession } from '../storage/googlePhotosSession.ts'
import {
  isGoogleUnauthorizedError,
  requestGooglePhotosAccessToken,
  type RequestGooglePhotosTokenOptions,
} from './googleAuth.ts'

function normalizeTokenOptions(
  options: RequestGooglePhotosTokenOptions | string = {},
): RequestGooglePhotosTokenOptions {
  return typeof options === 'string' ? { baseUrl: options } : options
}

/** Get a Photos token (cached or GIS) and retry once after HTTP 401. */
export async function withGooglePhotosAccessToken<T>(
  action: (accessToken: string) => Promise<T>,
  options: RequestGooglePhotosTokenOptions | string = {},
): Promise<T> {
  const opts = normalizeTokenOptions(options)
  const token = await requestGooglePhotosAccessToken(opts)
  try {
    return await action(token)
  } catch (error) {
    if (!isGoogleUnauthorizedError(error)) {
      throw error
    }
    clearGooglePhotosSession()
    const fresh = await requestGooglePhotosAccessToken({ ...opts, force: true })
    return await action(fresh)
  }
}
