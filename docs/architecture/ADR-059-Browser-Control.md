# ADR-059: Browser Control Architecture (Playwright)

## Status

Accepted — 2026-03-19

## Context

LIA needs to interact with websites beyond simple page fetching (web_fetch).
Use cases: fill forms, search products on e-commerce sites, extract dynamic
JS-rendered content, navigate multi-page workflows.

## Decision

### Architecture: Connector pattern with autonomous ReAct agent

Browser control follows the same connector pattern as Wikipedia:
- Infrastructure in `src/infrastructure/browser/` (pool, session, security, accessibility)
- Primary tool: `browser_task_tool` — takes a natural language task, delegates to a
  ReAct agent that navigates, searches, clicks, fills autonomously
- Internal tools: `browser_navigate_tool`, `browser_snapshot_tool`, `browser_click_tool`,
  `browser_fill_tool`, `browser_press_key_tool` — used by the ReAct loop, not by the planner
- Activation via admin connector panel (no `.env` feature flag)

### Key decisions

1. **`--no-sandbox` in Docker** — Required because Docker containers don't provide
   user namespaces. Isolation is ensured by the container itself.

2. **CDP direct for accessibility tree** — `await page.context.new_cdp_session(page)`
   + `Accessibility.getFullAXTree`. Stable Chrome DevTools Protocol API (Playwright's
   `page.accessibility.snapshot()` is deprecated since v1.41).

3. **Session-per-user with Redis recovery** — Sessions are process-local (Playwright
   BrowserContext can't be serialized). Metadata (URL, title) stored in Redis with TTL.
   Cross-worker recovery: re-navigate to stored URL transparently.

4. **Autonomous ReAct agent** — The planner calls `browser_task_tool` with a natural
   language instruction. The tool runs `create_react_agent` (langgraph.prebuilt) with
   browser tools internally. This enables multi-step interaction (navigate → search →
   click → read) that a static ExecutionPlan can't achieve.

5. **Content extraction via `page.inner_text()`** — Navigate returns visible text content
   (not raw AX tree). Tries semantic HTML5 containers (`main`, `article`) first, falls back
   to `body`. The AX tree is reserved for `snapshot` (interaction with [EN] refs).

6. **Anti-detection** — Chrome UA, `navigator.webdriver` removed, `AutomationControlled`
   disabled, locale/timezone from user preferences. Generic cookie banner auto-dismiss.

## Consequences

- Browser is the most resource-intensive agent (Chromium ~300-600MB RAM per session)
- Sites with strong anti-bot (DataDome, Cloudflare Turnstile) may still block
- ReAct loop adds latency (~15-60s per task) and token cost (~$0.01-0.03)
- Redis coordinates logical user sessions; container resource limits and measured
  workloads remain necessary for memory planning.

## Amendment 2026-10-02 — the engine is Debian's chromium package

**Measured.** Production ran Playwright 1.60's bundled Chromium 148, out of Chrome's
support since 2026-06-02 — four months of security fixes missing, in the container that
holds the secrets, with decision 1 above removing Chromium's own sandbox. Raising
Playwright does not close the gap: Chrome now ships a stable release every two weeks
(endoflife.date: 153 supported from 2026-09-08 to 2026-09-22) and Playwright every five
to seven, so the newest Playwright, 1.63, bundled a Chromium already out of support.

**Decision.** The API images install Debian's own `chromium` package (trixie-security,
amd64 and arm64) without its recommends and declare it through
`BROWSER_CHROMIUM_EXECUTABLE=/usr/bin/chromium`; `BrowserPool.initialize` passes it to
Playwright as `executable_path`, and Playwright (1.63) stays the driver. In the
production image that layer follows the provenance ARGs, which differ at every deploy
and release, so each build re-resolves the package: the engine is the stable release
Debian ships at build time, without a Playwright bump — and it ages, like every package
of the image, until the next build. The packages are signed, where `playwright install`
fetched an unchecked archive, and the package declares its own libraries, where the
image kept a hand-written list. Unset (a host run), Playwright starts its bundled build.

**Proven before adopting.** Playwright 1.63 driving Debian's Chromium 154.0.8037.92,
with the pool's arguments, on amd64 and on the production Raspberry Pi (arm64), in
throwaway containers: launch, `Accessibility.getFullAXTree` through CDP, click, fill,
screenshot. The bundled 153 passed the same probe — it works, it is just not supported.

**Consequences.**
- Playwright is released against its bundled build; it also supports driving Chrome's
  stable channel, which is where an engine one release ahead of its own stands. That is
  why the pair was measured (above) rather than assumed, and why a launch the driver
  cannot make any more is counted (`browser_errors_total{error_type="launch_failed"}`,
  dashboard 20), the driver it started is stopped rather than left running, and the
  engine that runs is logged at launch (`browser_pool_initialized chromium=… executable=…`).
- An empty `BROWSER_CHROMIUM_EXECUTABLE` reads as unset: compose hands an empty `.env`
  key to the process as an empty string, which would otherwise name a binary "".
- The sandbox stays off; moving the browser into an isolated container of its own is the
  next step (dependency programme, decision D7).

## Amendment 2026-10-15 — atomic admission and current context ownership

The pool reserves a logical user session before allocating its Playwright
context. A single bounded Redis hash (`browser:pool:registry`) stores the owner
UUID, recovery metadata and Redis-time expiry together. Each user's hash field
expires independently through [Redis hash-field expiration](https://redis.io/docs/latest/commands/hpexpireat/),
available in the Redis 7.4 provided by the current Compose and installer. A
no-effect capability/permission probe runs before any write; unsupported expiry
refuses admission instead of leaving a partly written, non-expiring record.
Admission and expiry
pruning are atomic; renewals, updates and release compare that UUID. A previous
owner cannot overwrite or delete a newer context's URL, and a reused PID does
not prevent recovery. Expired entries are pruned on every operation so another
user's renewals do not keep obsolete private metadata indefinitely.

Each pool maintains its own idle and ownership cleanup on every worker, without
depending on the scheduler leader. A context whose allocation lost ownership
is refused before it can be lent, with an attempt to close it. Failed or cancelled admissions attempt cleanup
without replacing their primary error. Shutdown waits for an allocation already
in progress, drains it and joins the local maintenance task. Recovery URLs and
titles have explicit bounds; an oversized URL is omitted rather than truncated
into a different request. The old per-user keys are read only as a transitional
URL fallback and expire naturally.

Same-user recovery retains the existing logical-session contract. Contexts may
overlap while ownership transfers or a worker is paused. Redis failure still
permits a bounded local pool for availability, so this is not a hard global
physical-memory guarantee. Redis recovery retires unregistered or superseded
contexts instead of reviving their metadata. All workers must use the same
coordination protocol and settings; mixed-version rolling operation is not
qualified here. The current Chromium arguments still disable its own sandbox;
container isolation has not been demonstrated equivalent to that sandbox.

Real Redis tests use independent pool owners and simulated Playwright contexts
to reproduce admission races, stale writes, PID reuse, expiry, cancellation,
shutdown and metadata bounds. They do not by themselves qualify a live Chromium
process or a remote website. Startup is coalesced across concurrent requests and
shielded from cancellation of an individual waiter. In-flight session operations
are excluded from idle retirement, with their activity clock reset on exit.
Shutdown attempts all resource closures before reporting the first failure.

The unused memory-limit setting, unsampled gauge and process-RSS helper have been
removed. The dashboard reuses the existing API-worker RSS sampler and labels it
as such; it excludes Chromium children and does not enforce a Chromium memory cap.

## References

- [BROWSER_CONTROL.md](../technical/BROWSER_CONTROL.md) — Technical documentation
- [SECURITY.md](../technical/SECURITY.md) — Browser security section
