import { vi } from 'vitest'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export type FetchRequestInfo = {
  url: string
  method: string
  path: string
  search: string
  init?: RequestInit
}

export type FetchHandler = (
  request: FetchRequestInfo,
) => Response | Promise<Response | null | undefined> | null | undefined

function parseRequest(input: RequestInfo | URL, init?: RequestInit): FetchRequestInfo {
  const url = String(input)
  const q = url.indexOf('?')
  return {
    url,
    method: (init?.method ?? 'GET').toUpperCase(),
    path: q === -1 ? url : url.slice(0, q),
    search: q === -1 ? '' : url.slice(q + 1),
    init,
  }
}

function pathMatches(actual: string, expected: string): boolean {
  return actual === expected || actual.endsWith(expected)
}

/** Strategy for answering `fetch` in tests. */
export abstract class FetchMockStrategy {
  abstract handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response>
}

/** Ordered scripted handlers; first non-null response wins. */
export class ScriptedFetchStrategy extends FetchMockStrategy {
  private readonly handlers: FetchHandler[] = []
  private fallback: FetchHandler = () => jsonResponse({ detail: 'not found' }, 404)

  on(handler: FetchHandler): this {
    this.handlers.push(handler)
    return this
  }

  onMethod(
    method: string,
    pathOrPred: string | ((request: FetchRequestInfo) => boolean),
    body: unknown,
    status = 200,
  ): this {
    const expected = method.toUpperCase()
    return this.on((request) => {
      if (request.method !== expected) {
        return null
      }
      if (typeof pathOrPred === 'string') {
        if (!pathMatches(request.path, pathOrPred) && !request.url.includes(pathOrPred)) {
          return null
        }
      } else if (!pathOrPred(request)) {
        return null
      }
      return jsonResponse(body, status)
    })
  }

  onGet(
    pathOrPred: string | ((request: FetchRequestInfo) => boolean),
    body: unknown,
    status = 200,
  ): this {
    return this.onMethod('GET', pathOrPred, body, status)
  }

  onPost(
    pathOrPred: string | ((request: FetchRequestInfo) => boolean),
    body: unknown,
    status = 200,
  ): this {
    return this.onMethod('POST', pathOrPred, body, status)
  }

  onPatch(
    pathOrPred: string | ((request: FetchRequestInfo) => boolean),
    body: unknown,
    status = 200,
  ): this {
    return this.onMethod('PATCH', pathOrPred, body, status)
  }

  onDelete(
    pathOrPred: string | ((request: FetchRequestInfo) => boolean),
    body: unknown = null,
    status = 204,
  ): this {
    return this.on((request) => {
      if (request.method !== 'DELETE') {
        return null
      }
      if (typeof pathOrPred === 'string') {
        if (!pathMatches(request.path, pathOrPred) && !request.url.includes(pathOrPred)) {
          return null
        }
      } else if (!pathOrPred(request)) {
        return null
      }
      if (status === 204 && body === null) {
        return new Response(null, { status })
      }
      return jsonResponse(body, status)
    })
  }

  onJob(job: { id: string }, extra?: (request: FetchRequestInfo) => Response | null): this {
    return this.on((request) => {
      if (!request.url.includes(`/api/jobs/${job.id}`)) {
        return extra?.(request) ?? null
      }
      const custom = extra?.(request)
      if (custom) {
        return custom
      }
      if (request.method === 'GET' && request.path.endsWith(`/api/jobs/${job.id}`)) {
        return jsonResponse(job)
      }
      return null
    })
  }

  setFallback(handler: FetchHandler): this {
    this.fallback = handler
    return this
  }

  override async handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = parseRequest(input, init)
    for (const handler of this.handlers) {
      const result = await handler(request)
      if (result) {
        return result
      }
    }
    const fallback = await this.fallback(request)
    return fallback ?? jsonResponse({ detail: 'not found' }, 404)
  }
}

export type FetchMockFn = ReturnType<typeof vi.fn>

type ProgressListener = (event: ProgressEvent) => void
type VoidListener = () => void

/** Bridge XMLHttpRequest → fetch mock (also usable from tests that stub fetch directly). */
export function installXhrFetchBridge(fetchMock: FetchMockFn): void {
  class BridgedXHR {
    method = 'GET'
    url = ''
    status = 0
    responseText = ''
    readyState = 0
    private readonly listeners = new Map<string, VoidListener[]>()
    readonly upload = {
      listeners: new Map<string, ProgressListener[]>(),
      addEventListener(type: string, listener: ProgressListener) {
        const list = this.listeners.get(type) ?? []
        list.push(listener)
        this.listeners.set(type, list)
      },
    }

    open(method: string, url: string) {
      this.method = method
      this.url = url
      this.readyState = 1
    }

    setRequestHeader(_name: string, _value: string) {}

    addEventListener(type: string, listener: VoidListener) {
      const list = this.listeners.get(type) ?? []
      list.push(listener)
      this.listeners.set(type, list)
    }

    send(body?: Document | XMLHttpRequestBodyInit | null) {
      void this.dispatch(body)
    }

    private emit(type: string) {
      for (const listener of this.listeners.get(type) ?? []) {
        listener()
      }
    }

    private emitProgress(loaded: number, total: number) {
      const event = {
        lengthComputable: total > 0,
        loaded,
        total,
      } as ProgressEvent
      for (const listener of this.upload.listeners.get('progress') ?? []) {
        listener(event)
      }
    }

    private async dispatch(body?: Document | XMLHttpRequestBodyInit | null) {
      try {
        const init: RequestInit = {
          method: this.method,
          body: body as BodyInit | null | undefined,
        }
        const callFetch = fetchMock as unknown as (
          input: string,
          init?: RequestInit,
        ) => Promise<Response>
        const response = await callFetch(this.url, init)
        const text = await response.text()
        // Synthetic progress so UI progress-bar tests can observe completion.
        this.emitProgress(1, 1)
        this.status = response.status
        this.responseText = text
        this.readyState = 4
        this.emit('load')
        this.emit('readystatechange')
      } catch {
        this.readyState = 4
        this.emit('error')
        this.emit('readystatechange')
      }
    }
  }

  vi.stubGlobal(
    'XMLHttpRequest',
    vi.fn(function XHRBridge(this: BridgedXHR) {
      return new BridgedXHR()
    }),
  )
}

/** Installs a fetch strategy as the global `fetch` mock. */
export class FetchHarness {
  readonly strategy: ScriptedFetchStrategy
  mock: FetchMockFn | null = null

  constructor(strategy?: ScriptedFetchStrategy) {
    this.strategy = strategy ?? new ScriptedFetchStrategy()
  }

  install(): FetchMockFn {
    const strategy = this.strategy
    this.mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
      strategy.handle(input, init),
    )
    vi.stubGlobal('fetch', this.mock)
    installXhrFetchBridge(this.mock)
    return this.mock
  }

  uninstall(): void {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    this.mock = null
  }

  calls(): unknown[][] {
    return this.mock?.mock.calls ?? []
  }

  calledWith(urlPart: string, method?: string): boolean {
    return this.calls().some((call) => {
      const url = String(call[0])
      if (!url.includes(urlPart) && url !== urlPart) {
        return false
      }
      if (!method) {
        return true
      }
      const init = call[1] as RequestInit | undefined
      return (init?.method ?? 'GET').toUpperCase() === method.toUpperCase()
    })
  }

  requestBody(urlPart: string, method?: string): unknown {
    const match = this.calls().find((call) => {
      const url = String(call[0])
      if (!url.includes(urlPart) && url !== urlPart) {
        return false
      }
      if (!method) {
        return true
      }
      const init = call[1] as RequestInit | undefined
      return (init?.method ?? 'GET').toUpperCase() === method.toUpperCase()
    })
    const init = match?.[1] as RequestInit | undefined
    if (!init?.body || typeof init.body !== 'string') {
      return undefined
    }
    return JSON.parse(init.body) as unknown
  }
}
