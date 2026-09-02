import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import App from '../App.tsx'
import { setColorScheme } from '../lib/appearance.ts'
import { t } from '../lib/language.ts'
import { clearTrackedRuns } from '../lib/runTracker.ts'
import { toast } from '../lib/toast.ts'
import { FakeEventSource } from './events.ts'
import { FetchHarness, type FetchMockFn, type ScriptedFetchStrategy } from './http.ts'

export type RoutedRenderResult = RenderResult & {
  router: ReturnType<typeof createMemoryRouter>
}

/** MemoryRouter + RouterProvider render helper. */
export class MemoryRouterHarness {
  router: ReturnType<typeof createMemoryRouter> | null = null

  renderApp(path: string): RoutedRenderResult {
    return this.renderElement(<App />, path)
  }

  renderElement(element: ReactElement, path = '/'): RoutedRenderResult {
    this.router = createMemoryRouter([{ path: '*', element }], {
      initialEntries: [path],
    })
    return {
      router: this.router,
      ...render(<RouterProvider router={this.router} />),
    }
  }

  pathname(): string {
    return this.router?.state.location.pathname ?? ''
  }
}

/**
 * Base class for routed page / app tests: fetch strategy, EventSource fake,
 * toast/run tracker reset, MemoryRouter.
 */
export abstract class RoutedPageTestBase {
  readonly fetch = new FetchHarness()
  readonly routes = new MemoryRouterHarness()

  install(): FetchMockFn {
    FakeEventSource.install()
    toast.clear()
    clearTrackedRuns()
    this.configureFetch(this.fetch.strategy)
    return this.fetch.install()
  }

  teardown(): void {
    toast.clear()
    clearTrackedRuns()
    setColorScheme('light', false)
    document.title = t.documentTitle
    this.fetch.uninstall()
    // FetchHarness.uninstall clears all globals (incl. XHR bridge); restore SSE fake.
    FakeEventSource.install()
  }

  /** Register default fetch routes for the scenario. */
  protected configureFetch(_strategy: ScriptedFetchStrategy): void {}

  renderApp(path: string): RoutedRenderResult {
    return this.routes.renderApp(path)
  }

  renderInRouter(element: ReactElement, path = '/'): RoutedRenderResult {
    return this.routes.renderElement(element, path)
  }
}
