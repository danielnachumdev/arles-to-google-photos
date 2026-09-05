export type UploadProgressEvent = {
  loaded: number
  total: number
  /** 0–100 when `total` is known; otherwise 0. */
  percent: number
}

export type StoreProgressEvent = {
  current: number
  total: number
  /** 0–100 when `total` is known; otherwise 0. */
  percent: number
  jobId?: string
}

export type FormPostResult = {
  status: number
  bodyText: string
}

const NDJSON_ACCEPT = 'application/x-ndjson'

export type JobCreateNdjsonParse = {
  /** Final job object JSON (same shape as a classic 201 body), when present. */
  jobJson: string | null
  storeEvents: StoreProgressEvent[]
  errorDetail: unknown | null
}

/** Parse classic JSON job body or NDJSON store/done/error stream from create job. */
export function parseJobCreateBody(bodyText: string): JobCreateNdjsonParse {
  const trimmed = (bodyText || '').trim()
  if (!trimmed) {
    return { jobJson: null, storeEvents: [], errorDetail: null }
  }
  if (!trimmed.includes('\n') && trimmed.startsWith('{')) {
    try {
      const obj = JSON.parse(trimmed) as Record<string, unknown>
      if (obj.event === 'done' && obj.job && typeof obj.job === 'object') {
        return {
          jobJson: JSON.stringify(obj.job),
          storeEvents: [],
          errorDetail: null,
        }
      }
      if (obj.event === 'error') {
        return { jobJson: null, storeEvents: [], errorDetail: obj.detail ?? obj }
      }
      if (typeof obj.id === 'string') {
        return { jobJson: trimmed, storeEvents: [], errorDetail: null }
      }
    } catch {
      return { jobJson: trimmed, storeEvents: [], errorDetail: null }
    }
  }

  const storeEvents: StoreProgressEvent[] = []
  let jobJson: string | null = null
  let errorDetail: unknown | null = null
  for (const line of trimmed.split('\n')) {
    const text = line.trim()
    if (!text) {
      continue
    }
    let obj: Record<string, unknown>
    try {
      obj = JSON.parse(text) as Record<string, unknown>
    } catch {
      continue
    }
    if (obj.event === 'store') {
      const current = Number(obj.current) || 0
      const total = Number(obj.total) || 0
      const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
      storeEvents.push({
        current,
        total,
        percent,
        jobId: typeof obj.job_id === 'string' ? obj.job_id : undefined,
      })
      continue
    }
    if (obj.event === 'done' && obj.job && typeof obj.job === 'object') {
      jobJson = JSON.stringify(obj.job)
      continue
    }
    if (obj.event === 'error') {
      errorDetail = obj.detail ?? obj
      continue
    }
    if (typeof obj.id === 'string') {
      jobJson = text
    }
  }
  return { jobJson, storeEvents, errorDetail }
}

/**
 * POST multipart FormData via XHR so upload progress events are available.
 * (fetch has no reliable upload-progress API across browsers.)
 *
 * When ``streamStoreProgress`` is true, sends ``Accept: application/x-ndjson``
 * and reports durable-store progress from the response body as it arrives.
 */
export function postFormData(
  url: string,
  form: FormData,
  options?: {
    onProgress?: (event: UploadProgressEvent) => void
    onStoreProgress?: (event: StoreProgressEvent) => void
    streamStoreProgress?: boolean
  },
): Promise<FormPostResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    if (options?.streamStoreProgress) {
      xhr.setRequestHeader('Accept', NDJSON_ACCEPT)
    }

    let parsedChars = 0
    const seenStoreKeys = new Set<string>()

    const consumeResponseText = () => {
      if (!options?.onStoreProgress) {
        return
      }
      const text = xhr.responseText ?? ''
      // Only advance past complete lines so partial NDJSON is not dropped.
      const lastNl = text.lastIndexOf('\n')
      if (lastNl < parsedChars) {
        return
      }
      const complete = text.slice(parsedChars, lastNl + 1)
      parsedChars = lastNl + 1
      for (const line of complete.split('\n')) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('{')) {
          continue
        }
        try {
          const obj = JSON.parse(trimmed) as Record<string, unknown>
          if (obj.event !== 'store') {
            continue
          }
          const current = Number(obj.current) || 0
          const total = Number(obj.total) || 0
          const key = `${current}/${total}`
          if (seenStoreKeys.has(key)) {
            continue
          }
          seenStoreKeys.add(key)
          const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
          options.onStoreProgress({
            current,
            total,
            percent,
            jobId: typeof obj.job_id === 'string' ? obj.job_id : undefined,
          })
        } catch {
          // Non-JSON line — ignore until load.
        }
      }
    }

    xhr.upload.addEventListener('progress', (event) => {
      if (!options?.onProgress) {
        return
      }
      const total = event.lengthComputable ? event.total : 0
      const loaded = event.loaded
      const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
      options.onProgress({ loaded, total, percent })
    })

    xhr.addEventListener('progress', () => {
      consumeResponseText()
    })
    xhr.addEventListener('readystatechange', () => {
      if (xhr.readyState === 3 || xhr.readyState === 4) {
        consumeResponseText()
      }
    })

    xhr.addEventListener('load', () => {
      const raw = xhr.responseText ?? ''
      if (options?.streamStoreProgress) {
        const parsed = parseJobCreateBody(raw)
        for (const event of parsed.storeEvents) {
          const key = `${event.current}/${event.total}`
          if (!seenStoreKeys.has(key)) {
            seenStoreKeys.add(key)
            options.onStoreProgress?.(event)
          }
        }
        if (parsed.errorDetail != null && parsed.jobJson == null) {
          resolve({
            status: xhr.status >= 400 ? xhr.status : 500,
            bodyText: JSON.stringify({ detail: parsed.errorDetail }),
          })
          return
        }
        if (parsed.jobJson != null) {
          resolve({ status: xhr.status, bodyText: parsed.jobJson })
          return
        }
      }
      resolve({ status: xhr.status, bodyText: raw })
    })

    xhr.addEventListener('error', () => {
      reject(new TypeError('Network request failed'))
    })

    xhr.addEventListener('abort', () => {
      reject(new DOMException('The user aborted a request.', 'AbortError'))
    })

    xhr.send(form)
  })
}
