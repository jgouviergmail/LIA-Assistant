/**
 * Route interception helpers for hermetic E2E (audit F031).
 *
 * The app talks to its backend exclusively via same-origin relative URLs
 * (`/api/v1/*`, proxied by Next rewrites), so intercepting `**​/api/v1/**` in
 * the browser captures 100% of backend traffic — no server, LLM, or paid
 * provider is ever contacted.
 *
 * Ordering matters. Playwright consults route handlers in LIFO order (last
 * registered wins). We therefore install exactly ONE catch-all first (lowest
 * priority) that fails any un-mocked API call loudly, then register specific
 * mocks after it so they take precedence. Installing a catch-all per mock call
 * would shadow earlier specific routes — hence the single-install contract.
 */
import type { Page, Route } from '@playwright/test';

export interface MockRoute {
  /** Glob or RegExp matched against the full request URL. */
  url: string | RegExp;
  /** Restrict to one HTTP method (case-insensitive). Default: any method. */
  method?: string;
  /** Response status. Default: 200. */
  status?: number;
  /**
   * JSON-serialisable response body. Default: {}. Ignored when `handler` is
   * set. Typed `unknown` so any factory-built payload (a typed interface with
   * no index signature) is accepted — it is JSON.stringify'd verbatim.
   */
  json?: unknown;
  /** Full manual control; when set, `status`/`json` are ignored. */
  handler?: (route: Route) => Promise<void> | void;
}

/**
 * Install the single lowest-priority catch-all. Any `/api/v1/*` request not
 * matched by a specific mock is fulfilled 501 so a leaking call is a loud,
 * visible failure — never a silent hit on a real backend.
 */
export async function installApiCatchAll(page: Page): Promise<void> {
  await page.route('**/api/v1/**', async route => {
    await route.fulfill({
      status: 501,
      contentType: 'application/json',
      body: JSON.stringify({
        error: 'unmocked_api_call',
        method: route.request().method(),
        url: route.request().url(),
      }),
    });
  });
}

/**
 * Register specific mocks (each takes precedence over the catch-all). A method
 * mismatch falls through to the catch-all, so a wrong-method call still fails
 * loudly rather than matching by URL alone.
 */
export async function registerRoutes(page: Page, routes: MockRoute[]): Promise<void> {
  for (const r of routes) {
    await page.route(r.url, async (route, request) => {
      if (r.method && request.method().toUpperCase() !== r.method.toUpperCase()) {
        await route.fallback();
        return;
      }
      if (r.handler) {
        await r.handler(route);
        return;
      }
      await route.fulfill({
        status: r.status ?? 200,
        contentType: 'application/json',
        body: JSON.stringify(r.json ?? {}),
      });
    });
  }
}
