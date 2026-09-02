import '@testing-library/jest-dom/vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { t } from '../lib/language.ts'
import { toast, TOAST_DURATION_MS } from '../lib/toast.ts'
import { ToastHost } from './ToastHost.tsx'

function ToastShell() {
  return (
    <>
      <ToastHost />
      <Outlet />
    </>
  )
}

function renderHost(initialPath = '/') {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <ToastShell />,
        children: [
          { index: true, element: <div>home</div> },
          { path: 'jobs/:jobId', element: <div>job page</div> },
        ],
      },
    ],
    { initialEntries: [initialPath] },
  )
  return { router, ...render(<RouterProvider router={router} />) }
}

describe('ToastHost', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    toast.clear()
  })

  afterEach(() => {
    toast.clear()
    vi.useRealTimers()
  })

  it('renders the message and type class for each level', () => {
    renderHost()

    act(() => {
      toast.good('נשמר.')
      toast.bad('הפרסום נכשל')
      toast.warning('חסר תיאור')
      toast.regular('מתחברים…')
    })

    const statuses = screen.getAllByRole('status')
    expect(statuses).toHaveLength(4)
    expect(statuses[0]).toHaveClass('toast', 'toast--good')
    expect(statuses[0]).toHaveTextContent('נשמר.')
    expect(statuses[1]).toHaveClass('toast--bad')
    expect(statuses[1]).toHaveTextContent('הפרסום נכשל')
    expect(statuses[2]).toHaveClass('toast--warning')
    expect(statuses[3]).toHaveClass('toast--regular')
    expect(screen.getByText('נשמר.')).toHaveAttribute('dir', 'auto')
  })

  it('dismisses from the close control', () => {
    renderHost()
    act(() => {
      toast.bad('הפרסום נכשל')
    })

    fireEvent.click(screen.getByRole('button', { name: t.toastDismissAria }))
    expect(screen.queryByText('הפרסום נכשל')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('auto-dismisses after the type duration', () => {
    renderHost()
    act(() => {
      toast.good('נשמר.')
    })
    expect(screen.getByText('נשמר.')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(TOAST_DURATION_MS.good)
    })
    expect(screen.queryByText('נשמר.')).not.toBeInTheDocument()
  })

  it('renders a depleting progress bar for timed toasts', () => {
    renderHost()
    act(() => {
      toast.good('נשמר.')
    })

    const bar = screen.getByRole('status').querySelector('.toast__progress')
    expect(bar).toBeTruthy()
    expect(bar).toHaveAttribute('aria-hidden', 'true')
    expect((bar as HTMLElement).style.getPropertyValue('--toast-duration')).toBe(
      `${TOAST_DURATION_MS.good}ms`,
    )
  })

  it('uses a custom duration on the progress bar', () => {
    renderHost()
    act(() => {
      toast.warning('soon', 100)
    })

    const bar = screen.getByRole('status').querySelector('.toast__progress')
    expect(bar).toBeTruthy()
    expect((bar as HTMLElement).style.getPropertyValue('--toast-duration')).toBe('100ms')
  })

  it('omits the progress bar on sticky toasts', () => {
    renderHost()
    act(() => {
      toast.bad('stay', 0)
    })

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByRole('status').querySelector('.toast__progress')).toBeNull()
  })

  it('renders a React Router link and navigates without a full reload', () => {
    const { router } = renderHost()
    act(() => {
      toast.regular({
        message: t.toastRunSubmitted('#42'),
        href: '/jobs/job-42',
        linkLabel: t.toastOpenRun,
      })
    })

    const link = screen.getByRole('link', { name: t.toastOpenRun })
    expect(link).toHaveAttribute('href', '/jobs/job-42')
    expect(screen.getByText(t.toastRunSubmitted('#42'))).toBeInTheDocument()

    fireEvent.click(link)
    expect(router.state.location.pathname).toBe('/jobs/job-42')
    expect(screen.queryByRole('link', { name: t.toastOpenRun })).not.toBeInTheDocument()
  })

  it('renders an external album action alongside the run link', () => {
    renderHost()
    act(() => {
      toast.good({
        message: t.toastUploadDone('#7'),
        actions: [
          {
            href: 'https://photos.google.com/album/example',
            label: t.toastOpenAlbum,
            external: true,
          },
          { href: '/jobs/upload-7', label: t.toastOpenRun },
        ],
      })
    })

    const album = screen.getByRole('link', { name: t.toastOpenAlbum })
    expect(album).toHaveAttribute('href', 'https://photos.google.com/album/example')
    expect(album).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('link', { name: t.toastOpenRun })).toHaveAttribute(
      'href',
      '/jobs/upload-7',
    )
  })
})
