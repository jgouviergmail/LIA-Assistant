/**
 * Capability probe for cross-origin iframe embedding under COEP.
 *
 * A cross-origin-isolated document may only embed a nested document that opts
 * into COEP itself — unless the iframe carries the `credentialless` attribute,
 * which lifts the requirement. That attribute is Chromium-only: WebKit (every
 * browser on iOS) and Firefox do not implement it. Measured on WebKit 26.4 —
 * the Google Maps embed of the `interactive-map` skill is refused with
 * "Cancelled load … because it violates the resource's
 * Cross-Origin-Resource-Policy response header", leaving a framed blank area
 * with no error anywhere in the UI.
 *
 * Rendering an iframe we already know the engine will refuse is strictly worse
 * than not rendering it: the user gets a dead rectangle instead of a link they
 * can act on. This module answers, before render, whether the embed can work.
 *
 * Note the deliberate asymmetry with the widget's `credentialless` attribute:
 * the attribute is still emitted (it is what makes the embed work on Chromium
 * under `require-corp`), while this probe decides whether to attempt the embed
 * at all.
 */

/**
 * Whether this engine implements the `credentialless` iframe attribute.
 *
 * Chromium 110+ only. Exported so the failure log can report the fact that
 * explains most COEP refusals without duplicating the probe.
 */
export function engineSupportsCredentialless(): boolean {
  return (
    typeof HTMLIFrameElement !== 'undefined' && 'credentialless' in HTMLIFrameElement.prototype
  );
}

/**
 * Whether this document can embed a cross-origin frame that opts into nothing.
 *
 * Two ways to be safe:
 * - the document is not cross-origin isolated, so COEP imposes nothing on
 *   nested documents (the posture `COEP_MODE=credentialless` produces on
 *   WebKit, and the one a COEP-less deployment always has);
 * - the engine implements the `credentialless` attribute **and the caller
 *   actually applies it**. Capability alone is not enough: the widget only
 *   sets the attribute on trusted system-skill URLs, so an untrusted — or
 *   rehydrated-with-the-flag-cleared — frame is refused on Chromium too, and
 *   there the refusal is invisible (Chromium fires `load` on its error
 *   document, so the watchdog cannot see it either).
 *
 * @param options.credentiallessApplied - Whether the caller will render the
 *   `credentialless` attribute on this specific iframe.
 * @returns `true` when the embed is expected to load, `false` when it would be
 *   refused. Server-side rendering returns `true`: the value is only meaningful
 *   in a browser, and the optimistic answer keeps the markup identical between
 *   server and first client render (no hydration mismatch).
 */
export function canEmbedOpaqueCrossOriginFrame(options: {
  credentiallessApplied: boolean;
}): boolean {
  if (typeof window === 'undefined') return true;
  const isolated =
    typeof window.crossOriginIsolated === 'boolean' ? window.crossOriginIsolated : false;
  if (!isolated) return true;
  return options.credentiallessApplied && engineSupportsCredentialless();
}

/**
 * Whether `url` points at an origin other than this document's.
 *
 * Only cross-origin embeds are subject to the COEP rule above; a same-origin
 * frame (the MCP airlock shell) is never affected. Malformed URLs are treated
 * as cross-origin — the conservative answer, since we cannot prove otherwise.
 *
 * @param url - Absolute or relative URL the widget wants to embed.
 * @returns `true` when the URL resolves to a different origin.
 */
export function isCrossOriginUrl(url: string): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return new URL(url, window.location.href).origin !== window.location.origin;
  } catch {
    return true;
  }
}
