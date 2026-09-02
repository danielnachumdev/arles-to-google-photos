import { expect } from 'vitest'
import { messages } from '../lib/i18n/catalogs.ts'
import { APP_LANGUAGES, type AppLanguage, type MessageCatalog } from '../lib/i18n/messages.ts'

/** Contract for bilingual catalogs: same keys, interpolators present. */
export abstract class CatalogContract {
  abstract catalogs(): Record<string, MessageCatalog>

  assertRegisteredLanguages(expected: readonly string[] = APP_LANGUAGES): void {
    expect(Object.keys(this.catalogs()).sort()).toEqual([...expected].sort())
  }

  assertSameKeys(): string[] {
    const catalogs = Object.values(this.catalogs())
    const keys = catalogs.map((catalog) => Object.keys(catalog).sort())
    const first = keys[0] ?? []
    for (const next of keys.slice(1)) {
      expect(next).toEqual(first)
    }
    return first
  }

  assertMinKeyCount(min: number): void {
    expect(this.assertSameKeys().length).toBeGreaterThan(min)
  }

  he(): MessageCatalog {
    return this.catalogs().he
  }

  en(): MessageCatalog {
    return this.catalogs().en
  }
}

export class AppCatalogContract extends CatalogContract {
  override catalogs(): Record<AppLanguage, MessageCatalog> {
    return messages
  }
}
