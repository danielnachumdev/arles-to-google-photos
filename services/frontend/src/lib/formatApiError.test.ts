import {
  ApiError,
  apiErrorFromHttp,
  describeApiError,
  explainCaughtError,
  formatApiError,
  isNotFoundError,
  summarizeErrorBody,
  totalJobFilesBytes,
} from './formatApiError.ts'
import { messages } from './language.ts'

const en = messages.en

describe('summarizeErrorBody', () => {
  it('extracts FastAPI JSON detail strings', () => {
    expect(summarizeErrorBody('{"detail":"invalid album"}')).toBe('invalid album')
  })

  it('never returns raw HTML pages', () => {
    const html = `<!DOCTYPE html><html><head><title>413</title></head><body>
      <h1>Request Entity Too Large</h1><p>Your client issued a request that was too large.</p>
      </body></html>`
    const summary = summarizeErrorBody(html)
    expect(summary).toBe('Request Entity Too Large')
    expect(summary).not.toMatch(/<!DOCTYPE|<html|<body/i)
  })

  it('truncates long plain text', () => {
    const long = 'x'.repeat(250)
    expect(summarizeErrorBody(long).length).toBeLessThanOrEqual(201)
  })
})

describe('apiErrorFromHttp', () => {
  it('maps 413 HTML to payload_too_large', () => {
    const html = `<html><body>Error 413 (Request Entity Too Large)</body></html>`
    const err = apiErrorFromHttp(413, html)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('payload_too_large')
    expect(err.status).toBe(413)
    expect(err.message).toMatch(/^HTTP 413\b/)
    expect(err.message).not.toMatch(/<html/i)
  })

  it('maps body text Request Entity Too Large even without 413 status', () => {
    const err = apiErrorFromHttp(400, 'Request Entity Too Large')
    expect(err.code).toBe('payload_too_large')
  })

  it('maps JSON detail for ordinary errors', () => {
    const err = apiErrorFromHttp(400, '{"detail":"invalid album"}')
    expect(err.code).toBe('http')
    expect(err.detail).toBe('invalid album')
    expect(err.message).toBe('HTTP 400: invalid album')
  })

  it('maps unknown 500 with concise fallback message', () => {
    const err = apiErrorFromHttp(500, '{"detail":"boom"}')
    expect(err.code).toBe('http')
    expect(err.message).toBe('HTTP 500: boom')
  })

  it('maps 401 to unauthorized', () => {
    const err = apiErrorFromHttp(401, '{"detail":"invalid token"}')
    expect(err.code).toBe('unauthorized')
    expect(err.message).toMatch(/^HTTP 401\b/)
  })

  it('maps 503 not configured to auth_not_configured', () => {
    const err = apiErrorFromHttp(503, '{"detail":"not configured"}')
    expect(err.code).toBe('auth_not_configured')
  })

  it('uses empty-body fallback without dumping', () => {
    const err = apiErrorFromHttp(502, '')
    expect(err.message).toBe('HTTP 502')
    expect(err.detail).toBe('')
  })
})

describe('formatApiError / describeApiError', () => {
  it('formats 413 as friendly payload message (no index.html advice)', () => {
    const err = apiErrorFromHttp(
      413,
      '<html><h1>Request Entity Too Large</h1></html>',
    )
    const message = formatApiError(err, en)
    expect(message).toBe(en.errorPayloadTooLarge)
    expect(message).not.toMatch(/index\.html|hrimages/i)
    expect(message).not.toMatch(/<html/i)
  })

  it('formats legacy HTTP 413 Error strings', () => {
    const legacy = new Error(
      'HTTP 413: <html><body>Request Entity Too Large</body></html>',
    )
    expect(formatApiError(legacy, en)).toBe(en.errorPayloadTooLarge)
  })

  it('uses JSON detail in unknown HTTP fallback', () => {
    expect(formatApiError(apiErrorFromHttp(500, '{"detail":"server exploded"}'), en)).toBe(
      'HTTP 500: server exploded',
    )
  })

  it('formats network / Failed to fetch', () => {
    expect(formatApiError(new TypeError('Failed to fetch'), en)).toBe(en.errorNetwork)
    expect(describeApiError(new TypeError('Failed to fetch'), en).standalone).toBe(true)
  })

  it('formats unauthorized and auth-not-configured as standalone', () => {
    expect(formatApiError(apiErrorFromHttp(401, '{}'), en)).toBe(en.errorUnauthorized)
    expect(
      formatApiError(new Error('Google OAuth is not configured on the server'), en),
    ).toBe(en.errorAuthNotConfigured)
  })
})

describe('explainCaughtError', () => {
  it('skips action wrappers for payload_too_large', () => {
    const err = apiErrorFromHttp(413, 'Request Entity Too Large')
    const wrapped = explainCaughtError(
      err,
      (detail) => `Could not build the preview. Make sure index.html. ${detail}`,
      en,
    )
    expect(wrapped).toBe(en.errorPayloadTooLarge)
    expect(wrapped).not.toMatch(/index\.html/)
  })

  it('wraps ordinary HTTP details', () => {
    const err = apiErrorFromHttp(400, '{"detail":"invalid album"}')
    expect(explainCaughtError(err, (d) => `Preview failed. ${d}`, en)).toBe(
      'Preview failed. HTTP 400: invalid album',
    )
  })
})

describe('isNotFoundError', () => {
  it('detects ApiError with HTTP 404', () => {
    expect(isNotFoundError(apiErrorFromHttp(404, '{"detail":"job not found"}'))).toBe(true)
    expect(isNotFoundError(apiErrorFromHttp(500, '{"detail":"boom"}'))).toBe(false)
    expect(isNotFoundError(new Error('HTTP 404: job not found'))).toBe(true)
    expect(isNotFoundError(new Error('network down'))).toBe(false)
    expect(isNotFoundError('nope')).toBe(false)
  })
})

describe('totalJobFilesBytes', () => {
  it('sums blob sizes', () => {
    expect(
      totalJobFilesBytes([
        { blob: new Blob([new Uint8Array(100)]) },
        { blob: new Blob([new Uint8Array(50)]) },
      ]),
    ).toBe(150)
  })
})
