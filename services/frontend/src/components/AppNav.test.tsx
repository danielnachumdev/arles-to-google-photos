import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { t } from '../lib/language.ts'
import { APP_VERSION } from '../version.ts'
import { AppNav } from './AppNav.tsx'

describe('AppNav', () => {
  it('marks the active route and links to every primary page', () => {
    render(
      <MemoryRouter initialEntries={['/jobs']}>
        <AppNav />
      </MemoryRouter>,
    )

    expect(screen.getByRole('navigation', { name: t.navAria })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.appTitle })).toHaveAttribute('href', '/')
    expect(screen.getByText(t.settingsVersionValue(APP_VERSION))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: t.navHome })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: t.navAlbums })).toHaveAttribute('href', '/albums')
    expect(screen.getByRole('link', { name: t.navJobs })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: t.navSettings })).toHaveAttribute('href', '/settings')
  })
})
