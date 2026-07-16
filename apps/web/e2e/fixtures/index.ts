/**
 * Extended Playwright test with hermetic API isolation + auth mocking (F031).
 *
 * Every test gets the API catch-all installed automatically (auto fixture, so
 * it is the lowest-priority route). `mockApi` registers higher-priority
 * specific mocks; `authenticate` seeds a session cookie and mocks `/auth/me`
 * with a deterministic user so authenticated pages render without a backend.
 */
import { test as base, expect } from '@playwright/test';
import { installApiCatchAll, registerRoutes, type MockRoute } from './api-mock';
import { dashboardShellMocks } from './dashboard-shell';
import { makeTestUser, type TestUser } from './test-user';

interface Fixtures {
  /** Auto-installed lowest-priority catch-all (un-mocked API → 501). */
  _apiIsolation: void;
  /** Register specific API mocks (win over the catch-all). */
  mockApi: (routes: MockRoute[]) => Promise<void>;
  /** Seed a session cookie and mock /auth/me so the app renders as signed-in. */
  authenticate: (overrides?: Partial<TestUser>) => Promise<TestUser>;
}

export const test = base.extend<Fixtures>({
  _apiIsolation: [
    async ({ page }, use) => {
      await installApiCatchAll(page);
      await use();
    },
    { auto: true },
  ],

  mockApi: async ({ page }, use) => {
    await use((routes) => registerRoutes(page, routes));
  },

  authenticate: async ({ page, context }, use) => {
    await use(async (overrides) => {
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
