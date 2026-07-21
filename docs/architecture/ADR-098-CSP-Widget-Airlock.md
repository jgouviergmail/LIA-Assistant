# ADR-098: CSP Widget Airlock — Per-Document Policies for Third-Party Widgets

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-096](ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md) (wave-3 audit that introduced the strict CSP), [ADR-093](ADR-093-Security-Hardening-Proxy-XSS.md) (XSS hardening), [MCP_INTEGRATION.md](../technical/MCP_INTEGRATION.md)

> [!NOTE]
> **Completed by [ADR-136](ADR-136-COEP-Posture-And-Widget-Failure-States.md) (2026-07-21).** This ADR restored the widgets on Chromium; WebKit was never verified. Under `COEP: require-corp` the interactive-map embed is refused by every iOS browser, because the lift depends on the Chromium-only `credentialless` iframe attribute. ADR-136 moves the default posture to `COEP: credentialless` and gives every widget a failure state. The airlock design itself is unchanged and was re-verified on WebKit — its four locks pass and the payload is delivered.

## Context

The wave-3 audit (A4, ADR-096) introduced a strict Content-Security-Policy
on every web response — a genuine XSS defense-in-depth. It shipped with
**three blind regressions**, all discovered at runtime, because a CSP change
had no test coverage and the policy's consumers were never inventoried:

1. **Voice input (push-to-talk AND wake-word mode)** — five code paths load
   JS from `blob:` URLs: the PTT `AudioWorklet` (`useVoiceInput`), the KWS +
   recording `AudioWorklet`s (`useVoiceMode`), and the Sherpa WASM glue
   `<script src=blob:>` loader (`sherpaKws`). Per CSP L3, a worklet's fetch
   destination is `audioworklet` — governed by **`script-src`**, *not*
   `worker-src` (which did allowlist `blob:`, but only covers real Workers).
2. **interactive-map skill** — its Google Maps embed (`frame.url`) was
   blocked because no `frame-src` was declared, so the directive fell back
   to `default-src 'self'`.
3. **MCP App widgets (Excalidraw, …)** — rendered in `srcDoc` iframes, which
   **inherit the parent document's CSP with no way to relax it from inside**.
   Third-party widgets load their runtime from CDNs (`esm.sh`: React,
   morphdom, CSS, fonts) — all blocked by the strict `script-src`.

Fixes 1 and 2 are directive corrections. Fix 3 is architectural: allowlisting
`esm.sh` in the app policy would (a) not scale (the next widget uses another
CDN — per-host whack-a-mole), (b) weaken the *whole app's* policy for the
benefit of content that is already fully isolated by its iframe sandbox, and
(c) foreclose a future nonce-based `script-src` where host allowlists become
the weak link.

## Decision

**Give third-party widgets their own document, and therefore their own CSP.**

A CSP is bound to an HTTP *response*, not an origin. `McpAppWidget` no longer
renders `srcDoc`; it points its sandboxed iframe at a same-origin static
shell — `/widget-frame.html` — whose response carries a dedicated,
deliberately permissive policy, and delivers the widget HTML via
`postMessage` on load. The shell `document.write()`s that HTML: the Window
persists, so the JSON-RPC bridge (`useMcpAppBridge`) is untouched — origin
stays the opaque `"null"`, `contentWindow` identity survives.

```
LIA app (strict CSP — unchanged)
 └─ <iframe src="/widget-frame.html"
            sandbox="allow-scripts …">        ← same sandbox as before
      response carries the AIRLOCK CSP (script/style/font/connect https:)
      └─ shell receives {type:'lia:widget-html', html} → document.write()
```

Key properties:

- **The app policy stays fully strict.** No CDN host ever enters it — the
  airlock absorbs every future widget CDN with zero policy churn.
- **Isolation is unchanged.** Widget containment never came from the CSP; it
  comes from `sandbox` without `allow-same-origin` (opaque origin: no
  cookies, no storage, no parent DOM). The airlock CSP's one real security
  directive is `frame-ancestors 'self'`.
- **Both policies live in `src/lib/csp.ts`**, a pure module imported by
  `next.config.ts` *and* by unit tests — every feature-bearing directive is
  now pinned by a non-regression test (`src/lib/__tests__/csp.test.ts`).

### Shell hardening (`public/widget-frame.html`)

The only new attack surface is the shell itself: if it ever executed a
delivered payload **unsandboxed**, that payload would run under the real LIA
origin, with cookies. Locks, in depth:

1. Refuses to run when not sandboxed (`window.origin !== 'null'`).
2. Refuses to run when top-level (`window === window.top`).
3. Accepts the payload only from `event.source === window.parent`.
4. Accepts it only from `event.origin === location.origin` (the LIA app) —
   rejects sibling widgets and escaped popups (origin `"null"`/foreign).
5. Single-shot: the first valid payload wins; later ones are ignored.
6. Response headers: `frame-ancestors 'self'` + `X-Frame-Options: SAMEORIGIN`
   (no external site can even embed the shell), `Referrer-Policy: no-referrer`,
   `COEP: require-corp` (required for a nested document under a COEP parent).

### Header routing

The global `headers()` rule now uses a path-to-regexp negative lookahead
(`/((?!widget-frame\.html).*)`) so the shell is excluded from the strict
policy — two CSP headers on one response would enforce their *intersection*
and silently re-block the airlock.

## Alternatives considered

- **Allowlist `esm.sh` in the app CSP** — rejected: whack-a-mole per CDN,
  weakens the whole app, blocks future nonce hardening. (Honest note: with
  `'unsafe-inline'` already required by Next.js bootstrap scripts, the
  *immediate* marginal risk would have been small — the rejection is
  architectural, not tactical.)
- **Dedicated widget origin** (`widgets.…`, the ChatGPT `web-sandbox` model)
  — the "textbook" answer, rejected as disproportionate: DNS + certificate +
  reverse-proxy + prod-tunnel changes on the RPi5, for a benefit the sandbox
  already provides. The airlock delivers the same policy separation with one
  static file. If widgets ever need `allow-same-origin` (persistent storage),
  revisit with a real second origin.
- **Nested `srcDoc` inside the shell** (inherits the shell's permissive CSP)
  — kept as documented fallback if `document.write` ever misbehaves; requires
  a message relay, so more moving parts. Not needed: module scripts AND
  importmaps through `document.write` were validated E2E (React 19 + morphdom
  loaded from esm.sh through the airlock).

## Consequences

- Excalidraw and any CDN-based MCP App widget render again; future widgets
  need no CSP change at all.
- User-skill `frame.html` widgets intentionally stay on `srcDoc`: they are
  self-contained by design and keep the *stricter* backend-injected meta-CSP
  (`skills/output_builder.py`) — the airlock is for third-party MCP content
  only.
- `apps/web/src/lib/csp.ts` is the single source of truth for both policies;
  editing a directive without updating its pinned test fails CI.
- The shell is a new deliverable in `public/` — it ships with the standard
  build, no infra change, dev/prod parity.

## Validation (2026-07-04, dev container)

- Headers: app routes carry exactly one strict CSP; `/widget-frame.html`
  carries exactly one airlock CSP (+ COEP/XFO/Referrer). Exclusion verified.
- E2E through the airlock: bare `import` from `esm.sh` ✅, importmap with bare
  specifier ✅ (the Apps SDK pattern).
- Voice: `AudioWorklet.addModule(blob:)` loads without violation ✅.
- Maps embed: `https://www.google.com/maps/embed` iframe fires `load` ✅.
- Negative: hostile sibling-iframe payload rejected ✅; second payload
  ignored (single-shot) ✅; unsandboxed inertness guaranteed by locks 1–2.
- Suite: 145/145 vitest (22 new), `tsc --noEmit` and ESLint clean.
