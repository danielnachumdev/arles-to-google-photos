import { describe, expect, it } from 'vitest'
import { createLocalStorageStore, type KeyValueStore } from './kv.ts'

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(initial))
  return {
    get length() {
      return map.size
    },
    clear() {
      map.clear()
    },
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null
    },
    key(index: number) {
      return [...map.keys()][index] ?? null
    },
    removeItem(key: string) {
      map.delete(key)
    },
    setItem(key: string, value: string) {
      map.set(String(key), String(value))
    },
  }
}

function throwingStorage(): Storage {
  const boom = (): never => {
    throw new Error('private mode')
  }
  return {
    get length() {
      return boom()
    },
    clear: boom,
    getItem: boom,
    key: boom,
    removeItem: boom,
    setItem: boom,
  }
}

describe('createLocalStorageStore', () => {
  it('returns null for a missing key', () => {
    const kv: KeyValueStore = createLocalStorageStore(memoryStorage())
    expect(kv.get('language')).toBeNull()
  })

  it('sets and gets a value', () => {
    const kv = createLocalStorageStore(memoryStorage())
    kv.set('language', 'he')
    expect(kv.get('language')).toBe('he')
  })

  it('overwrites an existing key', () => {
    const kv = createLocalStorageStore(memoryStorage({ language: 'he' }))
    kv.set('language', 'en')
    expect(kv.get('language')).toBe('en')
  })

  it('does not crash when storage throws', () => {
    const kv = createLocalStorageStore(throwingStorage())
    expect(kv.get('language')).toBeNull()
    expect(() => kv.set('language', 'en')).not.toThrow()
    expect(kv.get('language')).toBeNull()
  })

  it('uses window.localStorage when no backing store is passed', () => {
    window.localStorage.clear()
    const kv = createLocalStorageStore()
    expect(kv.get('language')).toBeNull()
    kv.set('language', 'en')
    expect(kv.get('language')).toBe('en')
    expect(window.localStorage.getItem('language')).toBe('en')
    window.localStorage.clear()
  })
})
