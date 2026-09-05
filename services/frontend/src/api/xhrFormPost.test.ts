import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  parseJobCreateBody,
  postFormData,
  type StoreProgressEvent,
  type UploadProgressEvent,
} from './xhrFormPost.ts'

type ProgressListener = (event: ProgressEvent) => void
type VoidListener = () => void

class FakeXHR {
  static instances: FakeXHR[] = []

  readonly upload = {
    listeners: new Map<string, ProgressListener[]>(),
    addEventListener(type: string, listener: ProgressListener) {
      const list = this.listeners.get(type) ?? []
      list.push(listener)
      this.listeners.set(type, list)
    },
    dispatch(type: string, event: ProgressEvent) {
      for (const listener of this.listeners.get(type) ?? []) {
        listener(event)
      }
    },
  }

  method = ''
  url = ''
  status = 0
  responseText = ''
  body: FormData | null = null
  private readonly listeners = new Map<string, VoidListener[]>()

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }

  setRequestHeader(_name: string, _value: string) {}

  addEventListener(type: string, listener: VoidListener) {
    const list = this.listeners.get(type) ?? []
    list.push(listener)
    this.listeners.set(type, list)
  }

  send(body?: Document | XMLHttpRequestBodyInit | null) {
    this.body = body instanceof FormData ? body : null
  }

  complete(status: number, bodyText: string) {
    this.status = status
    this.responseText = bodyText
    for (const listener of this.listeners.get('load') ?? []) {
      listener()
    }
  }

  failNetwork() {
    for (const listener of this.listeners.get('error') ?? []) {
      listener()
    }
  }

  emitProgress(loaded: number, total: number, lengthComputable = true) {
    this.upload.dispatch(
      'progress',
      {
        loaded,
        total,
        lengthComputable,
      } as ProgressEvent,
    )
  }
}

describe('postFormData', () => {
  beforeEach(() => {
    FakeXHR.instances = []
    vi.stubGlobal(
      'XMLHttpRequest',
      vi.fn(function MockXHR(this: FakeXHR) {
        const instance = new FakeXHR()
        FakeXHR.instances.push(instance)
        return instance
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('POSTs FormData and resolves status + body text', async () => {
    const form = new FormData()
    form.append('files', new Blob(['x']), 'a.txt')
    const pending = postFormData('/api/jobs', form)

    expect(FakeXHR.instances).toHaveLength(1)
    const xhr = FakeXHR.instances[0]!
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/jobs')
    expect(xhr.body).toBe(form)

    xhr.complete(201, '{"id":"job-1"}')
    await expect(pending).resolves.toEqual({ status: 201, bodyText: '{"id":"job-1"}' })
  })

  it('reports upload progress percent from XHR upload events', async () => {
    const form = new FormData()
    const events: UploadProgressEvent[] = []
    const pending = postFormData('/api/jobs?overwrite=true', form, {
      onProgress: (event) => events.push(event),
    })

    const xhr = FakeXHR.instances[0]!
    xhr.emitProgress(25, 100)
    xhr.emitProgress(100, 100)
    xhr.complete(200, '{}')
    await pending

    expect(events).toEqual([
      { loaded: 25, total: 100, percent: 25 },
      { loaded: 100, total: 100, percent: 100 },
    ])
  })

  it('uses percent 0 when length is not computable', async () => {
    const events: UploadProgressEvent[] = []
    const pending = postFormData('/api/jobs', new FormData(), {
      onProgress: (event) => events.push(event),
    })
    const xhr = FakeXHR.instances[0]!
    xhr.emitProgress(40, 0, false)
    xhr.complete(200, '{}')
    await pending
    expect(events).toEqual([{ loaded: 40, total: 0, percent: 0 }])
  })

  it('rejects on network error', async () => {
    const pending = postFormData('/api/jobs', new FormData())
    FakeXHR.instances[0]!.failNetwork()
    await expect(pending).rejects.toThrow(/network/i)
  })

  it('parses NDJSON store progress and resolves the done job', async () => {
    const store: StoreProgressEvent[] = []
    const pending = postFormData('/api/jobs', new FormData(), {
      streamStoreProgress: true,
      onStoreProgress: (event) => store.push(event),
    })
    const xhr = FakeXHR.instances[0]!
    const body =
      '{"event":"store","job_id":"j1","current":1,"total":2,"message":"Storing files"}\n' +
      '{"event":"store","job_id":"j1","current":2,"total":2,"message":"Storing files"}\n' +
      '{"event":"done","job":{"id":"j1","status":"pending"}}\n'
    xhr.complete(201, body)
    await expect(pending).resolves.toEqual({
      status: 201,
      bodyText: '{"id":"j1","status":"pending"}',
    })
    expect(store).toEqual([
      { current: 1, total: 2, percent: 50, jobId: 'j1' },
      { current: 2, total: 2, percent: 100, jobId: 'j1' },
    ])
  })
})

describe('parseJobCreateBody', () => {
  it('keeps a classic JSON job body', () => {
    const parsed = parseJobCreateBody('{"id":"job-1","status":"pending"}')
    expect(parsed.jobJson).toBe('{"id":"job-1","status":"pending"}')
    expect(parsed.storeEvents).toEqual([])
  })
})
