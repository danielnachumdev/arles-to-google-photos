import { vi } from 'vitest'
import type { JobEvent } from '../api/types.ts'

type MessageListener = (event: MessageEvent) => void

/** In-memory EventSource used by SSE subscribers in tests. */
export class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly url: string
  onmessage: MessageListener | null = null
  closed = false
  private readonly listeners = new Set<MessageListener>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  static reset(): void {
    FakeEventSource.instances = []
  }

  static install(): void {
    FakeEventSource.reset()
    vi.stubGlobal('EventSource', FakeEventSource)
  }

  static find(urlPart: string): FakeEventSource | undefined {
    return FakeEventSource.instances.find((source) => source.url.includes(urlPart))
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (type === 'message' && typeof listener === 'function') {
      this.listeners.add(listener as MessageListener)
    }
  }

  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ): void {
    if (type === 'message' && typeof listener === 'function') {
      this.listeners.delete(listener as MessageListener)
    }
  }

  close(): void {
    this.closed = true
  }

  emit(data: string | JobEvent): void {
    if (this.closed) {
      return
    }
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    const event = { data: payload } as MessageEvent
    this.onmessage?.(event)
    for (const listener of this.listeners) {
      listener(event)
    }
  }
}
