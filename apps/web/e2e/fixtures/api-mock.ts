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
  callbacks: Set<Promise<void>>;
  cancellation: AbortController;
  closing: boolean;
}

const isolations = new WeakMap<Page, ApiIsolation>();

function runRouteCallback(page: Page, callback: () => Promise<void>): Promise<void> {
  const isolation = isolations.get(page);
  const invocation = callback();
  isolation?.callbacks.add(invocation);
  return invocation.finally(() => isolation?.callbacks.delete(invocation));
}

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
  /** Full manual control; the signal cancels externally gated callbacks during teardown. */
  handler?: (route: Route, signal: AbortSignal) => Promise<void> | void;
}

/** An externally released test gate must also end when its owning test ends. */
export function waitForMockGate(gate: Promise<void>, signal: AbortSignal): Promise<boolean> {
  if (signal.aborted) return Promise.resolve(false);
  return new Promise((resolve, reject) => {
    const cancelled = () => {
      signal.removeEventListener('abort', cancelled);
      resolve(false);
    };
    signal.addEventListener('abort', cancelled, { once: true });
    void gate.then(
      () => {
        signal.removeEventListener('abort', cancelled);
        resolve(!signal.aborted);
      },
      (error: unknown) => {
        signal.removeEventListener('abort', cancelled);
        reject(error);
      }
    );
  });
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
  const isolation: ApiIsolation = {
    pending: new Map(),
    callbacks: new Set(),
    cancellation: new AbortController(),
    closing: false,
  };
  isolations.set(page, isolation);
  page.on('response', response => isolation.pending.delete(response.request()));
  page.on('requestfailed', request => isolation.pending.delete(request));
  page.on('close', () => isolations.delete(page));
  await page.route('**/api/v1/**', route =>
    runRouteCallback(page, async () => {
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
    })
  );
}

/** Cancel paused API requests before Firefox/WebKit delete their interception. */
export async function stopApiRequests(page: Page): Promise<void> {
  const isolation = isolations.get(page);
  if (!isolation || page.isClosed()) return;
  isolation.closing = true;
  isolation.cancellation.abort();
  // Closing a context can send unload beacons outside page routes. No further
  // network access is needed after the test; keep the document for artifacts.
  await page.context().setOffline(true);
  // A finite callback may still be preparing its response. Let it finish in
  // this test before aborting the routes left unanswered (including idle SSE).
  const callbacks = await Promise.allSettled([...isolation.callbacks]);
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
  for (const callback of callbacks) {
    if (callback.status === 'rejected') throw callback.reason;
  }
}

/**
 * Register specific mocks (each takes precedence over the catch-all). A method
 * mismatch falls through to the catch-all, so a wrong-method call still fails
 * loudly rather than matching by URL alone.
 */
export async function registerRoutes(page: Page, routes: MockRoute[]): Promise<void> {
  for (const r of routes) {
    await page.route(r.url, (route, request) =>
      runRouteCallback(page, async () => {
        if (r.method && request.method().toUpperCase() !== r.method.toUpperCase()) {
          await route.fallback();
          return;
        }
        if (!(await trackRoute(page, route))) return;
        if (r.handler) {
          const signal = isolations.get(page)?.cancellation.signal ?? new AbortController().signal;
          await r.handler(route, signal);
          return;
        }
        await route.fulfill({
          status: r.status ?? 200,
          contentType: 'application/json',
          body: JSON.stringify(r.json ?? {}),
        });
      })
    );
  }
}
