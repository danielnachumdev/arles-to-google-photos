import type { MessageCatalog } from './i18n/messages.ts'
import { t } from './language.ts'

export type ApiErrorCode =
  | 'payload_too_large'
  | 'unauthorized'
  | 'auth_not_configured'
  | 'network'
  | 'http'

export class ApiError extends Error {
  readonly status: number | undefined
  readonly code: ApiErrorCode
  readonly detail: string

  constructor(
    code: ApiErrorCode,
    options: { status?: number; detail?: string; message?: string } = {},
  ) {
    const status = options.status
    const detail = options.detail ?? ''
    const message =
      options.message ??
      (status != null
        ? detail
          ? `HTTP ${status}: ${detail}`
          : `HTTP ${status}`
        : detail || code)
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.detail = detail
  }
}

export type DescribedApiError = {
  code: ApiErrorCode | 'unknown'
  message: string
  status?: number
  /** When true, callers should show `message` as-is (no action wrapper). */
  standalone: boolean
}

const STANDALONE_CODES: ReadonlySet<ApiErrorCode> = new Set([
  'payload_too_large',
  'unauthorized',
  'auth_not_configured',
  'network',
])

function looksLikeHtml(body: string): boolean {
  const trimmed = body.trim().toLowerCase()
  return (
    trimmed.startsWith('<!doctype') ||
    trimmed.startsWith('<html') ||
    /<\s*html[\s>]/i.test(body)
  )
}

/** Extract a short, non-HTML detail from an HTTP error body. */
export function summarizeErrorBody(body: string): string {
  const trimmed = body.trim()
  if (!trimmed) {
    return ''
  }
  if (looksLikeHtml(trimmed)) {
    if (/request entity too large/i.test(trimmed)) {
      return 'Request Entity Too Large'
    }
    const text = trimmed
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    return text.slice(0, 120)
  }
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>
      if (typeof record.detail === 'string') {
        return record.detail
      }
      if (record.detail != null) {
        return JSON.stringify(record.detail).slice(0, 200)
      }
      if (typeof record.message === 'string') {
        return record.message
      }
    }
  } catch {
    // not JSON
  }
  if (trimmed.length > 200) {
    return `${trimmed.slice(0, 200)}…`
  }
  return trimmed
}

function isPayloadTooLarge(status: number, body: string): boolean {
  return status === 413 || /request entity too large/i.test(body)
}

function isAuthNotConfigured(status: number | undefined, bodyOrMessage: string): boolean {
  if (/google oauth is not configured/i.test(bodyOrMessage)) {
    return true
  }
  if (status === 503 && /not configured/i.test(bodyOrMessage)) {
    return true
  }
  return false
}

function catalogMessage(
  catalog: MessageCatalog,
  code: ApiErrorCode,
  status: number | undefined,
  detail: string,
): string {
  switch (code) {
    case 'payload_too_large':
      return catalog.errorPayloadTooLarge
    case 'unauthorized':
      return catalog.errorUnauthorized
    case 'auth_not_configured':
      return catalog.errorAuthNotConfigured
    case 'network':
      return catalog.errorNetwork
    case 'http':
      return catalog.errorHttpFallback(status ?? 0, detail)
    default:
      return detail
  }
}

/**
 * Build an ApiError from an HTTP status and response body (JSON, HTML, or plain).
 * Known cases get a stable `code`; Error.message stays machine-parseable (`HTTP N: …`).
 */
export function apiErrorFromHttp(status: number, body: string): ApiError {
  if (isPayloadTooLarge(status, body)) {
    return new ApiError('payload_too_large', {
      status: status === 413 ? 413 : status,
      detail: 'Request Entity Too Large',
      message: 'HTTP 413: Request Entity Too Large',
    })
  }
  const detail = summarizeErrorBody(body)
  if (status === 401) {
    return new ApiError('unauthorized', {
      status: 401,
      detail,
      message: detail ? `HTTP 401: ${detail}` : 'HTTP 401',
    })
  }
  if (isAuthNotConfigured(status, `${body} ${detail}`)) {
    return new ApiError('auth_not_configured', {
      status,
      detail,
      message: detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`,
    })
  }
  return new ApiError('http', {
    status,
    detail,
    message: detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`,
  })
}

export function totalJobFilesBytes(files: ReadonlyArray<{ blob: Blob }>): number {
  return files.reduce((sum, file) => sum + file.blob.size, 0)
}

function isNetworkFailure(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false
  }
  if (error instanceof ApiError) {
    return error.code === 'network'
  }
  const msg = error.message
  if (
    /failed to fetch/i.test(msg) ||
    /networkerror/i.test(msg) ||
    /load failed/i.test(msg) ||
    /network request failed/i.test(msg)
  ) {
    return true
  }
  return error.name === 'TypeError' && /fetch|network/i.test(msg)
}

const HTTP_MESSAGE_RE = /^HTTP (\d{3})\b(?:\s*:\s*)?(.*)$/s

/** True when the failure is an HTTP 404 (missing or forbidden-as-not-found). */
export function isNotFoundError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 404
  }
  if (error instanceof Error) {
    const match = HTTP_MESSAGE_RE.exec(error.message)
    return match != null && Number(match[1]) === 404
  }
  return false
}

export function describeApiError(
  error: unknown,
  catalog: MessageCatalog = t,
): DescribedApiError {
  if (error instanceof ApiError) {
    const message = catalogMessage(catalog, error.code, error.status, error.detail)
    return {
      code: error.code,
      message,
      status: error.status,
      standalone: STANDALONE_CODES.has(error.code),
    }
  }

  if (isNetworkFailure(error)) {
    return {
      code: 'network',
      message: catalog.errorNetwork,
      standalone: true,
    }
  }

  if (error instanceof Error) {
    if (isAuthNotConfigured(undefined, error.message)) {
      return {
        code: 'auth_not_configured',
        message: catalog.errorAuthNotConfigured,
        standalone: true,
      }
    }
    const match = HTTP_MESSAGE_RE.exec(error.message)
    if (match) {
      const status = Number(match[1])
      const rest = (match[2] ?? '').trim()
      if (isPayloadTooLarge(status, rest) || isPayloadTooLarge(status, error.message)) {
        return {
          code: 'payload_too_large',
          message: catalog.errorPayloadTooLarge,
          status: 413,
          standalone: true,
        }
      }
      if (status === 401) {
        return {
          code: 'unauthorized',
          message: catalog.errorUnauthorized,
          status: 401,
          standalone: true,
        }
      }
      if (isAuthNotConfigured(status, rest)) {
        return {
          code: 'auth_not_configured',
          message: catalog.errorAuthNotConfigured,
          status,
          standalone: true,
        }
      }
      const detail = summarizeErrorBody(rest)
      return {
        code: 'http',
        message: catalog.errorHttpFallback(status, detail),
        status,
        standalone: false,
      }
    }
    const trimmed = error.message.trim()
    return {
      code: 'unknown',
      message: trimmed || catalog.errorHttpFallback(0, ''),
      standalone: false,
    }
  }

  const text = String(error).trim()
  return {
    code: 'unknown',
    message: text || catalog.errorHttpFallback(0, ''),
    standalone: false,
  }
}

/** User-facing string for any thrown value or HTTP failure. */
export function formatApiError(error: unknown, catalog: MessageCatalog = t): string {
  return describeApiError(error, catalog).message
}

/**
 * Prefer a known standalone message; otherwise wrap a concise detail with `wrap`.
 */
export function explainCaughtError(
  error: unknown,
  wrap: (detail: string) => string,
  catalog: MessageCatalog = t,
): string {
  const described = describeApiError(error, catalog)
  if (described.standalone) {
    return described.message
  }
  return wrap(described.message)
}
