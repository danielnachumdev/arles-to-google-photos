import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { t } from '../lib/language.ts'
import {
  COOKIE_KEYS,
  clearImportCookies,
  resetCookieStore,
  resetSettingsStore,
  setCookieStore,
  setSettingsStore,
  writeDefaultImportMode,
} from '../lib/settings.ts'
import { createMemoryCookieStore } from '../storage/cookies.ts'
import { SpyKvStore } from '../testing/index.ts'
import { ImportDesk } from './ImportDesk.tsx'

function renderDesk(onImportWeb = vi.fn(), onPreparePreview = vi.fn()) {
  return {
    onImportWeb,
    onPreparePreview,
    ...render(
      <ImportDesk
        busy={false}
        working={false}
        folderLabel=""
        fileCount={0}
        folderInputId="folder-pick"
        onFolder={vi.fn()}
        onPreparePreview={onPreparePreview}
        onImportWeb={onImportWeb}
      />,
    ),
  }
}

function switchToWeb(): void {
  fireEvent.click(screen.getByRole('radio', { name: t.importModeWeb }))
}

describe('ImportDesk', () => {
  beforeEach(() => {
    setCookieStore(createMemoryCookieStore())
    resetSettingsStore()
  })

  afterEach(() => {
    resetCookieStore()
    resetSettingsStore()
  })

  it('defaults to folder upload with auto-publish on, and can switch to web', () => {
    renderDesk()

    const radios = screen.getAllByRole('radio')
    expect(radios[0]).toHaveAccessibleName(t.importModeUpload)
    expect(radios[1]).toHaveAccessibleName(t.importModeWeb)
    expect(radios[0]).toBeChecked()

    expect(screen.getByRole('heading', { name: t.folderHeading })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.preparePreview })).toBeDisabled()
    expect(screen.queryByRole('button', { name: t.startWebImport })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: t.autoPublishLabel })).toBeChecked()

    switchToWeb()

    expect(screen.getByRole('heading', { name: t.webImportHeading })).toBeInTheDocument()
    expect(screen.getByLabelText(t.webUrlLabel)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t.startWebImport })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: t.cacheHeadersLabel })).toBeChecked()
    expect(screen.getByRole('radio', { name: t.importModeWeb })).toBeChecked()
    expect(screen.queryByRole('button', { name: t.preparePreview })).not.toBeInTheDocument()
  })

  it('honors the stored default import mode setting', () => {
    const kv = new SpyKvStore()
    setSettingsStore(kv)
    writeDefaultImportMode('web')

    renderDesk()

    expect(screen.getByRole('radio', { name: t.importModeWeb })).toBeChecked()
    expect(screen.getByRole('heading', { name: t.webImportHeading })).toBeInTheDocument()
  })

  it('submits gallery url and optional headers', () => {
    const { onImportWeb } = renderDesk()
    switchToWeb()

    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.change(screen.getByLabelText(t.headerNameLabel), {
      target: { value: 'X-Test-Header' },
    })
    fireEvent.change(screen.getByLabelText(t.headerValueLabel), {
      target: { value: 'fixture-value' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(onImportWeb).toHaveBeenCalledTimes(1)
    expect(onImportWeb).toHaveBeenCalledWith(
      'https://gallery.example/index.html',
      {
        'X-Test-Header': 'fixture-value',
      },
      true,
    )
  })

  it('submits url only when header rows are blank', () => {
    const { onImportWeb } = renderDesk()
    switchToWeb()

    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: '  https://gallery.example/day1/  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(onImportWeb).toHaveBeenCalledWith('https://gallery.example/day1/', undefined, true)
  })

  it('caches used headers when the toggle is on and prefills them on remount', () => {
    const cookies = createMemoryCookieStore()
    setCookieStore(cookies)

    const first = renderDesk()
    switchToWeb()
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.change(screen.getByLabelText(t.headerNameLabel), {
      target: { value: 'Cookie' },
    })
    fireEvent.change(screen.getByLabelText(t.headerValueLabel), {
      target: { value: 'session=abc' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(JSON.parse(cookies.get(COOKIE_KEYS.importHeaders)!)).toEqual({
      Cookie: 'session=abc',
    })

    first.unmount()
    renderDesk()
    switchToWeb()

    expect(screen.getByLabelText(t.headerNameLabel)).toHaveValue('Cookie')
    expect(screen.getByLabelText(t.headerValueLabel)).toHaveValue('session=abc')
  })

  it('does not write the headers cookie when the toggle is off', () => {
    const cookies = createMemoryCookieStore()
    setCookieStore(cookies)

    renderDesk()
    switchToWeb()
    fireEvent.click(screen.getByRole('checkbox', { name: t.cacheHeadersLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.change(screen.getByLabelText(t.headerNameLabel), {
      target: { value: 'Cookie' },
    })
    fireEvent.change(screen.getByLabelText(t.headerValueLabel), {
      target: { value: 'session=abc' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(cookies.get(COOKIE_KEYS.importHeaders)).toBeNull()
    expect(cookies.get(COOKIE_KEYS.cacheHeaders)).toBe('0')
  })

  it('can turn off auto-publish for web import', () => {
    const { onImportWeb } = renderDesk()
    switchToWeb()

    fireEvent.click(screen.getByRole('checkbox', { name: t.autoPublishLabel }))
    fireEvent.change(screen.getByLabelText(t.webUrlLabel), {
      target: { value: 'https://gallery.example/index.html' },
    })
    fireEvent.click(screen.getByRole('button', { name: t.startWebImport }))

    expect(onImportWeb).toHaveBeenCalledWith(
      'https://gallery.example/index.html',
      undefined,
      false,
    )
  })

  it('passes auto-publish by default when preparing a folder preview', () => {
    const onPreparePreview = vi.fn()
    render(
      <ImportDesk
        busy={false}
        working={false}
        folderLabel="Day1"
        fileCount={3}
        folderInputId="folder-pick"
        onFolder={vi.fn()}
        onPreparePreview={onPreparePreview}
        onImportWeb={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: t.preparePreview }))
    expect(onPreparePreview).toHaveBeenCalledWith(true)
  })

  it('starts with empty import fields after settings clear', () => {
    setCookieStore(
      createMemoryCookieStore({
        [COOKIE_KEYS.importHeaders]: JSON.stringify({ Cookie: 'session=abc' }),
      }),
    )
    clearImportCookies()

    renderDesk()
    switchToWeb()

    expect(screen.getByLabelText(t.headerNameLabel)).toHaveValue('')
    expect(screen.getByLabelText(t.headerValueLabel)).toHaveValue('')
  })
})
