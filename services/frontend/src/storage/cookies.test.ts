import { afterEach, describe, expect, it } from 'vitest'
import { createDocumentCookieStore, createMemoryCookieStore, type CookieStore } from './cookies.ts'

function clearDocumentCookies(): void {
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0]?.trim()
    if (name) {
      document.cookie = `${encodeURIComponent(name)}=; path=/; max-age=0`
    }
  }
}

describe('createMemoryCookieStore', () => {
  it('returns null for a missing key', () => {
    const store: CookieStore = createMemoryCookieStore()
    expect(store.get('demo.key')).toBeNull()
  })

  it('sets and gets a value', () => {
    const store = createMemoryCookieStore()
    store.set('demo.key', 'demo')
    expect(store.get('demo.key')).toBe('demo')
  })

  it('overwrites an existing key', () => {
    const store = createMemoryCookieStore({ 'demo.key': 'demo' })
    store.set('demo.key', 'other')
    expect(store.get('demo.key')).toBe('other')
  })

  it('removes a key', () => {
    const store = createMemoryCookieStore({ 'demo.key': 'demo', 'other.key': 'secret' })
    store.remove('demo.key')
    expect(store.get('demo.key')).toBeNull()
    expect(store.get('other.key')).toBe('secret')
  })

  it('clears all keys', () => {
    const store = createMemoryCookieStore({
      'demo.key': 'demo',
      'arles.import.headers': '{"Cookie":"session=abc"}',
    })
    store.clear()
    expect(store.get('demo.key')).toBeNull()
    expect(store.get('arles.import.headers')).toBeNull()
  })
})

describe('createDocumentCookieStore', () => {
  afterEach(() => {
    clearDocumentCookies()
  })

  it('sets, gets, removes, and clears via document.cookie', () => {
    const store = createDocumentCookieStore()
    expect(store.get('demo.key')).toBeNull()

    store.set('demo.key', 'demo')
    store.set('other.key', 'secret')
    expect(store.get('demo.key')).toBe('demo')
    expect(store.get('other.key')).toBe('secret')

    store.remove('demo.key')
    expect(store.get('demo.key')).toBeNull()
    expect(store.get('other.key')).toBe('secret')

    store.clear()
    expect(store.get('other.key')).toBeNull()
  })

  it('round-trips JSON header maps', () => {
    const store = createDocumentCookieStore()
    const payload = JSON.stringify({ Cookie: 'session=abc' })
    store.set('arles.import.headers', payload)
    expect(store.get('arles.import.headers')).toBe(payload)
  })
})
