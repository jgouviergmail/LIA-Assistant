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
import type { Page, Request, Route } from '@playwright/test';

interface ApiIsolation {
  pending: Map<Request, Route>;
  closing: boolean;
}

const isolations = new WeakMap<Page, ApiIsolation>();

async function trackRoute(page: Page, route: Route): Promise<boolean> {
  const isolation = isolations.get(page);
  if (!isolation) return true;
  if (isolation.closing) {
    await route.abort('aborted');
    return false;
  }
  isolation.pending.set(route.request(), route);
  return true;
}

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
 * The person's real-time channel, saying nothing — the request is never answered.
 *
 * Left pending, it stays open the way an idle stream does, and the hook does
 * nothing at all. Every answer DROPS the channel: `status: 204` tells an
 * EventSource to fail (HTML spec), which Firefox logs as a JavaScript error on
 * every reconnection, and a complete body ends the stream, after which the
 * hook reconnects every 3 s and resyncs the conversation (`onReconnected`).
 */
export const idleNotificationStream: MockRoute = {
  url: '**/api/v1/notifications/stream',
  // Deliberately unanswered (no fulfill, continue or abort): the request hangs.
  handler: () => undefined,
};

/**
 * Install the single lowest-priority catch-all. Any `/api/v1/*` request not
 * matched by a specific mock is fulfilled 501 so a leaking call is a loud,
 * visible failure — never a silent hit on a real backend.
 */
export async function installApiCatchAll(page: Page): Promise<void> {
  const isolation: ApiIsolation = { pending: new Map(), closing: false };
  isolations.set(page, isolation);
  page.on('response', response => isolation.pending.delete(response.request()));
  page.on('requestfailed', request => isolation.pending.delete(request));
  page.on('close', () => isolations.delete(page));
  await page.route('**/api/v1/**', async route => {
    if (!(await trackRoute(page, route))) return;
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

/** Cancel paused API requests before Firefox/WebKit delete their interception. */
export async function stopApiRequests(page: Page): Promise<void> {
  const isolation = isolations.get(page);
  if (!isolation || page.isClosed()) return;
  isolation.closing = true;
  // Closing a context can send unload beacons outside page routes. No further
  // network access is needed after the test; keep the document for artifacts.
  await page.context().setOffline(true);
  const pending = [...isolation.pending.values()];
  const results = await Promise.allSettled(pending.map(route => route.abort('aborted')));
  for (const result of results) {
    if (result.status !== 'rejected') continue;
    const error: unknown = result.reason;
    // A response can finish between the response event and cancellation.
    if (error instanceof Error && error.message === 'Route is already handled!') continue;
    if (
      page.isClosed() &&
      error instanceof Error &&
      error.message.includes('Target page, context or browser has been closed')
    ) {
      continue;
    }
    throw error;
  }
  isolation.pending.clear();
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
      if (!(await trackRoute(page, route))) return;
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
