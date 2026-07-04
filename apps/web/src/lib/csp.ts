/**
 * Content-Security-Policy builders for the LIA web app (audit wave 3, A4 +
 * widget airlock follow-up).
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
    `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' blob:${isDev ? " 'unsafe-eval'" : ''}`,
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
    "font-src https: data:",
    "img-src https: data: blob:",
    "media-src https: data: blob:",
    "connect-src https: wss: data: blob:",
    "worker-src https: blob:",
    "frame-src https:",
    "form-action https:",
    "object-src 'none'",
    "base-uri 'none'",
    // CRITICAL — only the LIA app may embed this shell. Prevents external
    // sites from framing it without sandbox to launder script execution
    // under our origin.
    "frame-ancestors 'self'",
  ].join('; ');
}
