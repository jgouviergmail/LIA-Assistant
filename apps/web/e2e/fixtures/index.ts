/**
 * Extended Playwright test with hermetic API isolation + auth mocking (F031).
 *
 * Every test gets the API catch-all installed automatically (auto fixture, so
 * it is the lowest-priority route). `mockApi` registers higher-priority
 * specific mocks; `authenticate` seeds a session cookie and mocks `/auth/me`
 * with a deterministic user so authenticated pages render without a backend.
 */
import { test as base, expect } from '@playwright/test';
import { installApiCatchAll, registerRoutes, stopApiRequests, type MockRoute } from './api-mock';
import { createApiNetworkGuard, type ApiNetworkGuard } from './api-network-guard';
import { dashboardShellMocks } from './dashboard-shell';
import { makeTestUser, type TestUser } from './test-user';

interface Fixtures {
  apiNetworkGuard: ApiNetworkGuard;
  /** Auto-installed lowest-priority catch-all (un-mocked API → 501). */
  _apiIsolation: void;
  /** Register specific API mocks (win over the catch-all). */
  mockApi: (routes: MockRoute[]) => Promise<void>;
  /** Seed a session cookie and mock /auth/me so the app renders as signed-in. */
  authenticate: (overrides?: Partial<TestUser>) => Promise<TestUser>;
}

export const test = base.extend<Fixtures>({
  apiNetworkGuard: async ({ baseURL }, provide) => {
    if (baseURL && new URL(baseURL).protocol !== 'http:') {
      throw new Error('Hermetic E2E requires an HTTP app server; set E2E_BASE_URL to http://...');
    }
    const guard = await createApiNetworkGuard();
    try {
      await provide(guard);
    } finally {
      await guard.close();
    }
  },
  proxy: async ({ apiNetworkGuard }, provide) => {
    await provide(apiNetworkGuard.proxy);
  },
  _apiIsolation: [
    async ({ page, apiNetworkGuard }, provide) => {
      await installApiCatchAll(page);
      await provide();
      apiNetworkGuard.quarantine();
      await stopApiRequests(page);
    },
    { auto: true, timeout: 10_000 },
  ],

  mockApi: async ({ page }, provide) => {
    await provide(routes => registerRoutes(page, routes));
  },

  authenticate: async ({ page, context }, provide) => {
    await provide(async overrides => {
      const user = makeTestUser(overrides);
      // The real session cookie is HTTP-only and validated server-side; here
      // /auth/me is intercepted, so the value is irrelevant — we only seed a
      // cookie so any client code that merely checks for its presence is happy.
      await context.addCookies([
        { name: 'lia_session', value: 'e2e-session', domain: 'localhost', path: '/' },
      ]);
      // Shell mocks FIRST so any spec-registered mock (and /auth/me below)
      // takes precedence — Playwright routes are LIFO. The 501 catch-all
      // still guards everything not listed here or by the spec.
      await registerRoutes(page, dashboardShellMocks);
      await registerRoutes(page, [{ url: '**/api/v1/auth/me', json: user }]);
      return user;
    });
  },
});

export { expect };
export { makeTestUser } from './test-user';
export type { TestUser } from './test-user';
export type { MockRoute } from './api-mock';
export { idleNotificationStream, waitForMockGate } from './api-mock';
export { waitForHydration } from './hydration';
export { briefingCardsMock, briefingWindowsMock } from './dashboard-shell';
export { chatRoutes, loadedChatRoutes } from './chat';
export type { ChatBody } from './chat';
