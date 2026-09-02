import { vi } from 'vitest'
import type { KeyValueStore } from '../storage/kv.ts'
import { createMemoryCookieStore, type CookieStore } from '../storage/cookies.ts'

/** In-memory KeyValueStore strategy for language / settings tests. */
export class MemoryKvStore implements KeyValueStore {
  private readonly values: Map<string, string>

  constructor(initial: Record<string, string | null> = {}) {
    this.values = new Map(
      Object.entries(initial).filter((entry): entry is [string, string] => entry[1] != null),
    )
  }

  get(key: string): string | null {
    return this.values.has(key) ? this.values.get(key)! : null
  }

  set(key: string, value: string): void {
    this.values.set(key, value)
  }
}

/** Spying KV store that records writes. */
export class SpyKvStore implements KeyValueStore {
  readonly get = vi.fn((key: string): string | null => this.inner.get(key))
  readonly set = vi.fn((key: string, value: string): void => {
    this.inner.set(key, value)
  })
  private readonly inner: MemoryKvStore

  constructor(initial: Record<string, string | null> = {}) {
    this.inner = new MemoryKvStore(initial)
  }
}

export abstract class CookieStoreStrategy implements CookieStore {
  abstract get(key: string): string | null
  abstract set(key: string, value: string): void
  abstract remove(key: string): void
  abstract clear(): void
}

export class MemoryCookieStrategy extends CookieStoreStrategy {
  private readonly store: CookieStore

  constructor(initial: Record<string, string> = {}) {
    super()
    this.store = createMemoryCookieStore(initial)
  }

  static empty(): MemoryCookieStrategy {
    return new MemoryCookieStrategy()
  }

  override get(key: string): string | null {
    return this.store.get(key)
  }

  override set(key: string, value: string): void {
    this.store.set(key, value)
  }

  override remove(key: string): void {
    this.store.remove(key)
  }

  override clear(): void {
    this.store.clear()
  }
}
