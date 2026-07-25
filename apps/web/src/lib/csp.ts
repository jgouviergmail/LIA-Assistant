/**
 * Security-header builders for the LIA web app (audit wave 3, A4 + widget
 * airlock follow-up): Content-Security-Policy, HSTS and the
 * Cross-Origin-Embedder-Policy posture.
 *
 * They live in one pure module — shared with `src/lib/__tests__/csp.test.ts` —
 * so every value a runtime feature depends on is pinned by a test. Never
 * inline a header value in `next.config.ts`: three regressions shipped blind
 * that way (voice worklets, the interactive-map embed, and the COEP posture
 * that made every external embed fail on iOS).
 *
 * Two distinct policies coexist, each bound to its own HTTP response:
 *
 * 1. **App policy** (`buildAppCsp`) — strict, applied to every route EXCEPT
 *    the widget frame. Defense-in-depth against XSS: an injected
 *    `<script src>` or `eval()` is blocked even if a rendering bug ever
 *    reintroduces raw HTML.
 *
 * 2. **Widget-frame policy** (`buildWidgetFrameCsp`) — deliberately
 *    permissive, applied ONLY to `/widget-frame.html` (the "CSP airlock").
 *    Third-party MCP App widgets (e.g. Excalidraw) load their runtime from
 *    arbitrary CDNs (esm.sh, …). A `srcDoc` iframe inherits the parent
 *    document's CSP with no way to relax it from inside, so those widgets
 *    are instead bootstrapped into a real same-origin document that carries
 *    its own permissive policy. Their isolation does NOT come from CSP — it
 *    comes from the iframe `sandbox` attribute (opaque origin, no cookies,
 *    no storage, no parent DOM). The airlock CSP only hardens the shell
 *    itself against abuse (`frame-ancestors 'self'`).
 *
 * App-policy constraints honored:
 * - Next.js App Router ships inline bootstrap scripts → 'unsafe-inline' is
 *   required in script-src (no per-request nonce with static headers). The
 *   header still blocks every EXTERNAL script origin and eval().
 * - Sherpa-onnx voice mode compiles WASM → 'wasm-unsafe-eval' + blob: workers.
 * - Voice features load code from blob: URLs → blob: in script-src is
 *   required for: the push-to-talk STT AudioWorklet (useVoiceInput), the
 *   voice-mode KWS + recording AudioWorklets (useVoiceMode), and the Sherpa
 *   WASM glue `<script src=blob:>` loader (sherpaKws). Per CSP L3 a
 *   worklet's fetch destination is "audioworklet"/"paintworklet", governed
 *   by script-src, NOT worker-src.
 * - Skill widget iframes use srcDoc (inherit this CSP) and are
 *   self-contained by design — inline allowance keeps them working. The one
 *   external embed is the interactive-map system skill (Google Maps iframe)
 *   → frame-src allowlists https://www.google.com.
 * - MCP App widgets are NOT srcDoc anymore — they go through the widget
 *   airlock (see above) precisely because they are not self-contained.
 * - Google Fonts stylesheet + font files (see app/[lng]/layout.tsx).
 * - In production the API is a separate origin (NEXT_PUBLIC_API_URL) reached
 *   via fetch/SSE/WebSocket → connect-src includes it (+ ws(s) variant).
 * - Enrolling a device for push calls two Google APIs from the document →
 *   connect-src allowlists them (see FIREBASE_MESSAGING_CONNECT_SRC).
 * - Dev: turbopack HMR needs eval() and websockets.
 */

/** Path of the widget airlock shell (served from `public/`). */
export const WIDGET_FRAME_PATH = '/widget-frame.html';

/**
 * `headers()` source pattern applying the strict app policy to every route
 * except the widget frame (path-to-regexp negative lookahead — same engine
 * as middleware matchers). The widget frame gets its own headers entry; two
 * CSP headers on one response would enforce their INTERSECTION, which would
 * silently re-block the airlock.
 */
export const APP_HEADERS_SOURCE = '/((?!widget-frame\\.html).*)';

/**
 * Google hosts the Firebase Web Push SDK reaches FROM THE DOCUMENT when a user
 * enrolls a device (`getToken()` in src/lib/firebase.ts). Two sequential
 * fetches, both governed by connect-src:
 *
 *   1. `firebaseinstallations` — mints the short-lived FIS auth token;
 *   2. `fcmregistrations` — exchanges it (as a header) + the browser's push
 *      subscription for the FCM registration token we POST to the backend.
 *
 * Omitting them does NOT break push DELIVERY — that path is server →
 * firebase-admin → FCM → service worker, with no client call to Google. It
 * breaks ENROLMENT only. That asymmetry is why the gap shipped unnoticed on
 * 2026-07-03 with the first CSP (v1.21.5) and stayed invisible for three
 * weeks: every already-registered device kept receiving notifications, so the
 * failure only surfaced the day a user disabled notifications and could not
 * re-enable them — for anyone, including first-time activations.
 *
 * Keep them as two exact hosts: a wildcard would re-open every Google origin,
 * and no backend proxy can substitute for them (the SDK issues the fetches
 * itself, from the page).
 */
export const FIREBASE_MESSAGING_CONNECT_SRC = [
  'https://firebaseinstallations.googleapis.com',
  'https://fcmregistrations.googleapis.com',
] as const;

/**
 * Build the connect-src directive value for the app policy.
 *
 * @param isDev - Whether running in development mode (adds HMR websockets
 *   and the local API origins).
 * @param apiUrl - Value of NEXT_PUBLIC_API_URL ('' or undefined for
 *   same-origin deployments).
 * @returns The space-separated connect-src source list.
 */
export function buildConnectSrc(isDev: boolean, apiUrl: string | undefined): string {
  const sources = ["'self'"];
  if (apiUrl) {
    try {
      const origin = new URL(apiUrl).origin;
      sources.push(origin, origin.replace(/^http/, 'ws'));
    } catch {
      // Malformed URL — fall back to same-origin only
    }
  }
  // Push enrolment — required in dev too, or the feature cannot be tested
  sources.push(...FIREBASE_MESSAGING_CONNECT_SRC);
  if (isDev) {
    sources.push('ws:', 'wss:', 'http://localhost:8000', 'http://127.0.0.1:8000');
  }
  return sources.join(' ');
}

/**
 * Build the strict app Content-Security-Policy (every route except the
 * widget frame).
 *
 * @param isDev - Whether running in development mode.
 * @param apiUrl - Value of NEXT_PUBLIC_API_URL.
 * @returns The full policy string for the Content-Security-Policy header.
 */
export function buildAppCsp(isDev: boolean, apiUrl: string | undefined): string {
  return [
    "default-src 'self'",
    // blob: → voice AudioWorklets + Sherpa glue loader (see module docstring)
    // static.cloudflareinsights.com → the analytics beacon Cloudflare injects
    // at the edge in production; without the allowance it dies as a console
    // CSP error on every public page
    `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' blob: https://static.cloudflareinsights.com${isDev ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    // https: for user-facing remote images (chat markdown, connector data);
    // images are not a script vector and COEP already gates embedding
    "img-src 'self' data: blob: https:",
    "media-src 'self' data: blob:",
    "worker-src 'self' blob:",
    // 'self' → widget airlock + srcDoc frames; www.google.com → the
    // interactive-map system skill's Google Maps embed (frame.url), the only
    // external frame we ship. Without an explicit frame-src, the directive
    // falls back to default-src 'self' and blocks it.
    "frame-src 'self' https://www.google.com",
    `connect-src ${buildConnectSrc(isDev, apiUrl)}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
  ].join('; ');
}

/**
 * Cross-Origin-Embedder-Policy values LIA can emit on app documents.
 *
 * Both enable cross-origin isolation on Chromium (so the voice-mode wake word
 * keeps its `SharedArrayBuffer`); they differ in how a cross-origin resource
 * that opts into nothing is treated, and — critically — in what WebKit does
 * with them. Measured on WebKit 26.4 and Chromium, with the production headers
 * replicated and the real Google Maps embed of the `interactive-map` skill:
 *
 * | header value       | Chromium: isolated / map | WebKit: isolated / map |
 * |--------------------|--------------------------|------------------------|
 * | `require-corp`     | yes / yes                | yes / **blocked**      |
 * | `credentialless`   | yes / yes                | no  / yes              |
 *
 * `require-corp` demands that every embedded cross-origin document opt in via
 * its own COEP header. Google Maps sends none, so the embed only survives
 * because of the `credentialless` **attribute** on the iframe — which is
 * Chromium-only. On WebKit (every browser on iOS) the map document is refused
 * outright: "Cancelled load … because it violates the resource's
 * Cross-Origin-Resource-Policy response header". The user sees a framed blank
 * area with no error.
 *
 * `credentialless` (the **header** value, not the attribute) keeps isolation on
 * Chromium — no-cors subresources are simply fetched without credentials, so
 * the Spectre guarantee holds — while WebKit, which does not implement it,
 * falls back to no isolation and therefore embeds normally.
 *
 * The trade is deliberate and already handled by the product: without
 * isolation `isSherpaKwsSupported()` returns false and voice mode degrades to
 * tap-to-speak (no wake word) — a path that predates this change. Losing the
 * wake word on iOS is worth widgets that work on iOS.
 */
export type CoepMode = 'require-corp' | 'credentialless';

/**
 * Default COEP posture. See {@link CoepMode} for the measured trade-off.
 *
 * Env-tunable through `COEP_MODE`. NOT at runtime, despite what this comment
 * claimed until 2026-07-25: Next.js evaluates `headers()` from next.config.ts
 * at BUILD time and serialises the result into `.next/routes-manifest.json`
 * (verified — the manifest carries the literal header value). The standalone
 * server then replays the manifest, so changing the variable and restarting the
 * container changes nothing. A new value needs a rebuild, which `task
 * deploy:prod` performs on every deployment anyway.
 *
 * Any unrecognized value falls back to this default rather than emitting a
 * header the browser would ignore.
 */
export const DEFAULT_COEP_MODE: CoepMode = 'credentialless';

/**
 * Resolve the `Cross-Origin-Embedder-Policy` value to emit on app documents.
 *
 * @param raw - Value of the `COEP_MODE` environment variable, if any.
 * @returns `raw` when it names a supported mode, {@link DEFAULT_COEP_MODE}
 *   otherwise (absent, misspelled, or a value the platform would ignore).
 */
export function resolveCoepMode(raw: string | undefined): CoepMode {
  const normalized = raw?.trim().toLowerCase();
  return normalized === 'require-corp' || normalized === 'credentialless'
    ? normalized
    : DEFAULT_COEP_MODE;
}

/**
 * Default HSTS `max-age` in seconds — a conservative 1-day starting point.
 *
 * SEC-025 rolls HSTS out gradually: a browser remembers the HTTPS pin for
 * `max-age` seconds, so a long value is hard to walk back. Start short, confirm
 * the whole public surface is durably HTTPS, then raise `HSTS_MAX_AGE` toward
 * two years (63072000). Current production step: 2592000 (one month).
 *
 * This is the FALLBACK, and it stays at one day on purpose: a deployment that
 * forgot the variable should land on the conservative rung, not inherit the
 * boldest one. The step itself lives in `.env.prod.example`.
 *
 * The value is baked at build time (see {@link DEFAULT_COEP_MODE} for why), so
 * a new step reaches production through a rebuild — not a restart.
 *
 * The API emits this header too and reads the SAME variable
 * (`SecuritySettings.hsts_max_age`). It used to hardcode
 * `max-age=31536000; includeSubDomains; preload`, contradicting this very
 * policy on a surface browsers honour identically.
 *
 * `includeSubDomains` and `preload` are intentionally NOT emitted: both are
 * near-irreversible (the preload list is slow to leave, and the pin covers
 * every subdomain) and must not be enabled before a full subdomain inventory
 * proves each one is durably HTTPS — deliberately out of scope here (see the
 * cookie-scoping work, SEC-004).
 */
export const DEFAULT_HSTS_MAX_AGE = 86_400;

/**
 * Build the `Strict-Transport-Security` header value (SEC-025).
 *
 * @param maxAgeSeconds - Desired `max-age`; a non-finite or non-positive value
 *   falls back to {@link DEFAULT_HSTS_MAX_AGE}.
 * @returns e.g. `max-age=86400` — no `includeSubDomains`, no `preload`.
 */
export function buildHsts(maxAgeSeconds: number = DEFAULT_HSTS_MAX_AGE): string {
  const maxAge =
    Number.isFinite(maxAgeSeconds) && maxAgeSeconds > 0
      ? Math.floor(maxAgeSeconds)
      : DEFAULT_HSTS_MAX_AGE;
  return `max-age=${maxAge}`;
}

/**
 * Build the widget-frame ("CSP airlock") Content-Security-Policy.
 *
 * Philosophy: restore the pre-CSP environment for third-party widgets —
 * their containment is the iframe `sandbox` (opaque origin), which this
 * policy does not and cannot replace. The only directive doing real
 * security work here is `frame-ancestors 'self'`: it guarantees no external
 * site can embed the shell UNSANDBOXED and feed it hostile HTML that would
 * then run under the LIA origin (the shell also self-checks
 * `window.origin === 'null'` for the same reason — defense in depth).
 *
 * @returns The full policy string for the widget-frame response.
 */
export function buildWidgetFrameCsp(): string {
  return [
    "default-src 'none'",
    // Third-party widget runtimes: CDN modules (esm.sh, …), inline
    // bootstraps, wasm, occasionally eval-based bundles. blob: for
    // client-generated code. Contained by the sandbox, not by this list.
    "script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' https: blob:",
    "style-src 'unsafe-inline' https:",
    'font-src https: data:',
    'img-src https: data: blob:',
    'media-src https: data: blob:',
    'connect-src https: wss: data: blob:',
    'worker-src https: blob:',
    'frame-src https:',
    'form-action https:',
    "object-src 'none'",
    "base-uri 'none'",
    // CRITICAL — only the LIA app may embed this shell. Prevents external
    // sites from framing it without sandbox to launder script execution
    // under our origin.
    "frame-ancestors 'self'",
  ].join('; ');
}
