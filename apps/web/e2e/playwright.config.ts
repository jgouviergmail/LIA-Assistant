import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the LIA web E2E + a11y smoke suite (audit F031).
 *
 * Hermetic by design: every spec intercepts `**​/api/v1/**` (see fixtures/api-mock)
 * and serves fixed payloads, so the suite never depends on a running backend,
 * a real LLM, or any paid provider. Only a Next.js server serving the app is
 * required at `baseURL`.
 *
 * Execution model:
 *  - Local proof + CI run inside the official Playwright image (glibc); the
 *    Alpine dev container cannot run Playwright's bundled browsers.
 *  - `E2E_BASE_URL` points at an HTTP production server. Local proofs share
 *    the dev container's network namespace and use a separate server/port.
 *    The transport guard refuses opaque CONNECT tunnels.
 *  - Set `E2E_MANAGED_SERVER=1` to have Playwright build+serve the app itself
 *    (used by the CI job, where the app source is present in the same image).
 */
// Match the managed server's IPv4 HTTP contract, also used for local proofs.
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3000';
const useManagedServer = process.env.E2E_MANAGED_SERVER === '1';

export default defineConfig({
  testDir: '.',
  // The showroom specs assert the GUIDED build contract and the capture spec
  // records launch assets: both are meaningless (and red) against the default
  // legacy build, so they only run through their dedicated Task targets
  // (test:e2e:showroom[:telemetry|:capture]), which set E2E_SHOWROOM=1 and
  // name their spec files explicitly.
  // The LEADING `*` is load-bearing: without it the glob only matches a
  // FILENAME that starts with `public-demo-showroom`, so
  // `smoke/public-demo-showroom.spec.ts` was excluded while
  // `a11y/axe-public-demo-showroom.spec.ts` silently ran inside the default
  // suite — which builds the LEGACY variant. Its picker clicks then waited 90s
  // for an element that page never renders, and its one non-clicking test
  // ("mission picker has no blocking violation") passed VACUOUSLY by scanning
  // whatever `/demo` happened to serve. Measured in CI on 2026-08-08: six
  // failures whose page snapshot showed the legacy mockup, unreproducible
  // locally because a manual run passes E2E_SHOWROOM=1 and skips the trap.
  testIgnore:
    process.env.E2E_SHOWROOM === '1' ? [] : ['**/*public-demo-showroom*', '**/capture/**'],
  // Foundation is a PR smoke: keep it fast and deterministic. Firefox/WebKit
  // and the full zoom/reflow matrix are a documented periodic extension.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Against the dev container's `next dev`, parallel workers compile routes
  // on demand concurrently and corrupt the webpack dev cache (HTTP 500,
  // `JSON.parse` errors, ENOENT `0.pack.gz` — the server then stays broken
  // until `.next` is purged). ONE worker keeps the local run deterministic;
  // the CI managed server is a production build and handles 2 fine.
  workers: process.env.CI ? 2 : useManagedServer ? 2 : 1,
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }], ['list']]
    : [['html', { open: 'never' }], ['list']],
  // Generous timeouts absorb Next dev's on-demand compilation (first hit on a
  // route can take ~10s). The CI managed server is a production build, so it is
  // far faster there.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    navigationTimeout: 60_000,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // Deterministic viewport + reduced motion so animations never flake a scan.
    viewport: { width: 1280, height: 900 },
    contextOptions: { reducedMotion: 'reduce' },
    // The suite mocks every API call with `page.route`. The production build
    // registers the offline service worker (ADR-146), and once it controls the
    // page, WebKit sends the requests the worker hands back to the browser by a
    // path `page.route` never sees: they reached the real server and the chat
    // answered « Erreur serveur (500) ». Measured: 5-7 of 10 WebKit journeys
    // red, at random (whenever the worker took control first), 0 of 11 with
    // workers blocked. The worker's own behaviour has its unit test.
    serviceWorkers: 'block',
  },
  // Chromium is the fast PR smoke. Firefox/WebKit run in the periodic
  // browser-matrix job (.github/workflows/a11y-matrix.yml) or on demand with
  // E2E_ALL_BROWSERS=1 — same specs, engine-diverse evidence (AC-002).
  projects: [
    // The full bundled renderer uses Chrome's supported new headless mode.
    // It stays on Playwright's pinned revision and retains every audit rule.
    { name: 'chromium', use: { ...devices['Desktop Chrome'], channel: 'chromium' } },
    ...(process.env.E2E_ALL_BROWSERS === '1'
      ? [
          { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
          { name: 'webkit', use: { ...devices['Desktop Safari'] } },
        ]
      : []),
  ],
  webServer: useManagedServer
    ? {
        // The app lives one directory up. It builds with `output: 'standalone'`
        // (see next.config.ts / Dockerfile.prod), and `next start` DOES NOT
        // work with standalone output (Next refuses: "use node
        // .next/standalone/server.js instead") — public pages half-worked but
        // every authenticated scenario failed without the app shell. So:
        // build, copy the static assets + public/ into the standalone tree
        // (standalone deliberately excludes them — same layout as
        // Dockerfile.prod), then run the traced server.js. The monorepo build
        // roots the standalone tree at the repo root, hence `apps/web/` inside.
        // E2E_FORCE_FRESH=1 (showroom contract builds) purges .next first: a
        // NEXT_PUBLIC_* flag is baked at build time, so reusing a previous
        // build or server would silently test the WRONG variant (the exact
        // ADR-192 evidence trap — dev-server/stale-bundle proofs are void).
        command:
          '([ "$E2E_FORCE_FRESH" = "1" ] && rm -rf ../.next || true) && ' +
          'pnpm --dir .. build && ' +
          'rm -rf ../.next/standalone/apps/web/.next/static ../.next/standalone/apps/web/public && ' +
          'cp -r ../.next/static ../.next/standalone/apps/web/.next/static && ' +
          'cp -r ../public ../.next/standalone/apps/web/public && ' +
          'node ../.next/standalone/apps/web/server.js',
        // Through `env`, never a `VAR=value cmd` prefix: Playwright runs the
        // command in the platform's shell, and `cmd.exe` on a Windows host
        // reads that prefix as a program name — the build passed and the
        // server never started. Playwright merges this over `process.env`.
        env: { PORT: '3000', HOSTNAME: '0.0.0.0' },
        url: baseURL,
        reuseExistingServer: !process.env.CI && process.env.E2E_FORCE_FRESH !== '1',
        timeout: 300_000,
      }
    : undefined,
});
