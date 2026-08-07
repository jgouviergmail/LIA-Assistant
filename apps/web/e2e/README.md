# LIA Web — E2E & Accessibility Smoke (audit F031)

Hermetic end-to-end and WCAG smoke suite for the LIA web app, built on
[Playwright](https://playwright.dev) + [`@axe-core/playwright`](https://github.com/dequelabs/axe-core-npm).

## Why this is an isolated package

The dev container (`lia-web-dev`) runs **Alpine (musl)**, but Playwright ships
**glibc** browser binaries that cannot run there. So this suite lives in its own
package — **outside the pnpm workspace** (`apps/*`, not `apps/**`) — and always
runs inside the **official Playwright image** (glibc), both in CI and for local
proof. It never touches the app's `node_modules` or the root lockfile, and it
does not import app source (it drives a browser), so the isolation is natural.

## Hermetic by design

Every spec intercepts `**/api/v1/**` and serves fixed payloads (`fixtures/`), so
**no backend, LLM, or paid provider is ever contacted**. An auto fixture installs
a single lowest-priority catch-all that fails any un-mocked API call with `501`,
so a leaking request is a loud, visible failure — never a silent real hit.

- `fixtures/api-mock.ts` — catch-all + `registerRoutes` (LIFO ordering explained inline).
- `fixtures/test-user.ts` — deterministic `User` factory mirroring `src/lib/auth.tsx`.
- `fixtures/dashboard-shell.ts` — type-correct mocks for the endpoints the
  authenticated shell fires on every page (config, personalities, connector
  health, psyche state, usage limits, voice ticket, RAG-space pickers).
  Installed by `authenticate` BEFORE any spec mock, so specs override freely
  (routes are LIFO); anything not listed still hits the 501 catch-all.
- `fixtures/index.ts` — extended `test` with `mockApi` and `authenticate` (mocks
  `/auth/me` + shell endpoints + seeds a session cookie, so protected pages
  render signed-in).

## Layout

```
smoke/  public + authenticated user journeys (login, dashboard, chat, admin)
        + the landing mobile-overflow guard (375 px across the full hero
        animation cycle via the Playwright clock, per-section, 320 px reflow)
a11y/   axe WCAG 2.x A/AA scans — smoke pages + journeys (chat, settings,
        spaces, admin), public pages /faq + /demo in light AND dark (the
        theme is localStorage-driven, OS-scheme emulation does nothing),
        reflow 320 CSS px and 200 % zoom. color-contrast is BLOCKING
        (AC-002); per-node reports are archived as attachments.
```

PR scope is **Chromium** for speed. The same suite replays weekly on
Firefox/WebKit via `.github/workflows/a11y-matrix.yml` (or locally with
`E2E_ALL_BROWSERS=1`). The manual NVDA/VoiceOver campaign protocol is
versioned at `docs/a11y/AT_CAMPAIGN.md`; the token-level contrast contract at
`docs/a11y/CONTRAST_TOKENS.md`.

## Reproducible dependencies (audit F054)

`package.json` pins **exact versions** (no `^`/`~` ranges) and
`package-lock.json` (v3) is **committed**. Always install with `npm ci` — it
fails when the manifest and the lock diverge, which is the drift guard. After
changing a dependency, regenerate the lock inside the official image
(`npm install --package-lock-only`) and commit both files together.

## Running locally (against the dev container)

The dev container already serves the app over HTTPS on `:3000`. Run the suite in
the official Playwright image sharing that container's network namespace, so
`https://localhost:3000` is the container's `next dev`:

```bash
docker run --rm --network container:lia-web-dev \
  -v "//d/Developpement/LIA/apps/web/e2e:/e2e" -w /e2e \
  mcr.microsoft.com/playwright:v1.60.0-jammy \
  sh -c "npm ci --no-audit --no-fund && npx playwright test --reporter=list"
```

(On Git Bash, prefix with `MSYS_NO_PATHCONV=1` so the mount path is not rewritten.)

The default `baseURL` is `https://localhost:3000` with `ignoreHTTPSErrors` (the
dev cert is self-signed). Override with `E2E_BASE_URL` to target another server.

### Local PROOF runs: use a production server (recommended)

`next dev` is unsuitable as a proof target: beyond the cache-corruption trap
below, a page can stay **unstyled forever** (the CSS chunk never applies on a
fresh browser context, ~half of the scans on a loaded server) — the scan guard
then aborts loudly, but the run is red for a server reason, not an app reason.
For a stable local proof, build and serve a PRODUCTION bundle inside the dev
container on a separate port (separate `NEXT_DIST_DIR`, so the running
`next dev` and its `.next` are untouched — `NODE_ENV=production` is required:
the dev container exports `NODE_ENV=development`, under which `next build`
fails prerendering with `useContext` null errors):

The app builds with `output: standalone`, and **`next start` does not work
with standalone output** (Next says so explicitly; symptoms range from refusal
to public-pages-only). Serve the traced `server.js` instead — the exact layout
`Dockerfile.prod` ships (standalone excludes `.next/static` and `public/` by
design, copy them in):

```bash
docker exec -u node -e NODE_ENV=production -e NEXT_DIST_DIR=.next-e2e lia-web-dev \
  sh -c "cd /monorepo/apps/web && pnpm build"
docker exec -u node lia-web-dev sh -c "cd /monorepo/apps/web \
  && rm -rf .next-e2e/standalone/apps/web/.next-e2e/static .next-e2e/standalone/apps/web/public \
  && cp -r .next-e2e/static .next-e2e/standalone/apps/web/.next-e2e/static \
  && cp -r public .next-e2e/standalone/apps/web/public"
docker exec -d -u node -e NODE_ENV=production lia-web-dev sh -c \
  "cd /monorepo/apps/web && PORT=3100 HOSTNAME=0.0.0.0 node .next-e2e/standalone/apps/web/server.js"

docker run --rm --network container:lia-web-dev -e E2E_BASE_URL=http://127.0.0.1:3100 \
  -v "//d/Developpement/LIA/apps/web/e2e:/e2e" -w /e2e \
  mcr.microsoft.com/playwright:v1.60.0-jammy \
  sh -c "npm ci --no-audit --no-fund && npx playwright test --reporter=list"
```

`127.0.0.1`, not `localhost`: the standalone server binds IPv4-only
(`HOSTNAME=0.0.0.0`), and `localhost` may resolve to `::1` first (connection
refused — the recurring IPv6-first trap on this codebase).

Stop the production server afterwards with
`docker exec lia-web-dev sh -c "pkill -f 'standalone/apps/web/server.js'"` (or
restart the container). CI does the equivalent via `E2E_MANAGED_SERVER=1`
(same build → copy → `node server.js` sequence, wired in
`playwright.config.ts`).

### `next dev` stability (why local runs use ONE worker)

Parallel workers make `next dev` compile routes on demand concurrently, which
corrupts the webpack dev cache: HTTP 500, `SyntaxError: Unexpected
non-whitespace character` (`JSON.parse`), `ENOENT … 0.pack.gz` — and the server
**stays broken afterwards** until you purge its cache:

```bash
docker exec lia-web-dev sh -c "rm -rf /app/.next" && docker restart lia-web-dev
```

The config therefore pins `workers: 1` for non-managed (dev-server) runs; the
CI managed server is a production build and runs 2 workers fine.

A second dev-server trap: a page can be **interactive before the app
stylesheet is applied** (style chunks compile on demand). Scanning that
unstyled window produces phantom `color-contrast` violations — every `<a>`
falls back to Chromium's dark-UA link color (`#9e9eff`) over the default white
canvas, implicating the palette for a server hiccup. `a11y/scan.ts` therefore
waits for the design-system tokens to resolve before every scan and aborts
with an actionable error if they never do.

### Showroom suites from a Windows host

`task test:e2e:showroom` works in CI (Linux) but NOT from the Windows host:
the e2e `node_modules` are typically installed from a Linux container (no
`.cmd` shims, so `npx playwright` is "not recognized"), and the managed
server spawns `PORT=3000 node …`, an inline env assignment cmd.exe cannot
parse. The proven local sequence is the production-server recipe above with
the showroom build flags, then the suite in the official image:

```bash
docker exec -u node -e NODE_ENV=production -e NEXT_DIST_DIR=.next-e2e \
  -e NEXT_PUBLIC_API_URL= -e NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided \
  -e NEXT_PUBLIC_PRODUCT_TELEMETRY=false -e NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0 \
  lia-web-dev sh -c "cd /monorepo/apps/web && pnpm build"
# then the static/public copy + PORT=3100 server start, as above, and:
MSYS_NO_PATHCONV=1 docker run --rm --network container:lia-web-dev \
  -e E2E_BASE_URL=http://127.0.0.1:3100 -e E2E_SHOWROOM=1 \
  -v "//d/Developpement/LIA/apps/web/e2e:/e2e" -w /e2e \
  mcr.microsoft.com/playwright:v1.60.0-jammy \
  sh -c "npm ci --no-audit --no-fund && npx playwright test \
    smoke/public-demo-showroom.spec.ts a11y/axe-public-demo-showroom.spec.ts --reporter=list"
```

## Running in CI

The `e2e-frontend` job runs in the same Playwright image. It sets
`E2E_MANAGED_SERVER=1`, so Playwright builds and serves the app itself and
runs the smoke against it — no dev container, no backend. Because the app
builds with `output: standalone` (`next start` refuses that mode), the managed
command is: `next build`, copy `.next/static` and `public/` into
`.next/standalone/apps/web/` (standalone excludes them by design — same layout
as `Dockerfile.prod`), then `PORT=3000 HOSTNAME=0.0.0.0 node
.next/standalone/apps/web/server.js`. See `.github/workflows/ci.yml`.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `E2E_BASE_URL` | `https://localhost:3000` | Server under test. |
| `E2E_MANAGED_SERVER` | unset | `1` → Playwright builds + serves the app (CI). |
| `CI` | unset | Enables retries, GitHub reporter, `forbidOnly`. |
