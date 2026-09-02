export type UploadProgressEvent = {
  loaded: number
  total: number
  /** 0–100 when `total` is known; otherwise 0. */
  percent: number
}

export type FormPostResult = {
  status: number
  bodyText: string
}

/**
 * POST multipart FormData via XHR so upload progress events are available.
 * (fetch has no reliable upload-progress API across browsers.)
 */
export function postFormData(
  url: string,
  form: FormData,
  options?: { onProgress?: (event: UploadProgressEvent) => void },
): Promise<FormPostResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)

    xhr.upload.addEventListener('progress', (event) => {
      if (!options?.onProgress) {
        return
      }
      const total = event.lengthComputable ? event.total : 0
      const loaded = event.loaded
      const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0
      options.onProgress({ loaded, total, percent })
    })

    xhr.addEventListener('load', () => {
      resolve({ status: xhr.status, bodyText: xhr.responseText ?? '' })
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
