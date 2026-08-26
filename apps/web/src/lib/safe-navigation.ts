/**
 * Guarded full-page navigation to a URL that came back from the API.
 *
 * SEC-002 — several flows assign an API-supplied URL straight to
 * `window.location.href` to hand the browser over to an authorization server.
 * That assignment is a navigation primitive: a `javascript:` URL there does not
 * navigate at all, it EXECUTES in the LIA origin, with the session cookie and
 * the whole DOM in reach.
 *
 * For MCP the concern is concrete rather than theoretical, because the
 * authorization endpoint is discovered from metadata published by a server the
 * user added themselves — the value crosses a trust boundary before it reaches
 * this line. The backend already refuses a non-HTTPS or private-host endpoint
 * (`infrastructure/mcp/oauth_flow.py::_is_safe_endpoint`), so this is defence in
 * depth and not a hole being plugged. It earns its place by guarding the
 * primitive itself: the check no longer depends on every current AND future
 * endpoint remembering to validate before answering.
 */

import { logger } from '@/lib/logger';
import { isNativeShell, openInSystemBrowser } from '@/lib/native/shell';

/**
 * Schemes a redirect to an external authorization server may legitimately use.
 *
 * `http:` is allowed on purpose. It buys no attacker anything the browser would
 * not already permit — the executable schemes are the ones excluded — while
 * refusing it would break a locally hosted authorization server in development
 * for no security gain. Confidentiality of the OAuth exchange is enforced where
 * it belongs: the backend requires HTTPS for MCP endpoints.
 */
const ALLOWED_REDIRECT_PROTOCOLS: readonly string[] = ['http:', 'https:'];

/** Raised when a URL is not something we are willing to navigate to. */
export class UnsafeRedirectError extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = 'UnsafeRedirectError';
  }
}

/**
 * Whether this URL is an absolute http(s) URL, and therefore navigable.
 *
 * @param url - Candidate URL, straight off an API response.
 * @returns True when assigning it to `window.location` only navigates.
 */
export function isSafeRedirectUrl(url: unknown): url is string {
  if (typeof url !== 'string' || url.trim() === '') return false;

  try {
    // Relative URLs throw here, which is the right outcome: an authorization
    // endpoint is always absolute, and a relative value means the response was
    // not what we think it is.
    const parsed = new URL(url);
    // `protocol` is lowercased by the parser, so `JaVaScRiPt:` is covered.
    return ALLOWED_REDIRECT_PROTOCOLS.includes(parsed.protocol);
  } catch {
    return false;
  }
}

/**
 * Navigate the current tab to an API-supplied authorization URL.
 *
 * Inside a native shell the URL leaves for the SYSTEM browser instead. Google
 * refuses OAuth from an embedded webview outright (`disallowed_useragent`), so
 * navigating the WebView ends the flow before it starts. Eight flows funnel
 * through here — connectors, MCP, bulk connect, reconnection, sign-in — and
 * deciding it once is what spares each of them a branch nobody would remember
 * to add to the ninth.
 *
 * The safety check runs FIRST, so a shell is never a way around it.
 *
 * @param url - The `authorization_url` from the API response.
 * @param context - Short label identifying the flow, for the failure log.
 * @throws UnsafeRedirectError - When the URL is not an absolute http(s) URL.
 *   Thrown rather than silently ignored: every caller already reports failures
 *   to the user, and a click that does nothing at all is indistinguishable from
 *   a broken button.
 */
export function navigateToAuthorizationUrl(url: unknown, context: string): void {
  if (!isSafeRedirectUrl(url)) {
    // The URL itself is logged: it is the evidence, and at this point it is
    // already known to be something we refused to follow.
    logger.error(`Refused an unsafe authorization redirect (${context})`, undefined, {
      component: 'safe-navigation',
      context,
      url: typeof url === 'string' ? url.slice(0, 200) : typeof url,
    });
    throw new UnsafeRedirectError(
      'The authorization URL returned by the server is not a valid https address.'
    );
  }

  if (isNativeShell()) {
    // Not awaited: the signature stays synchronous for its eight callers, none
    // of which has anything to do after the browser has the URL.
    void openInSystemBrowser(url)
      .catch(() => false)
      .then((taken) => {
        if (!taken) {
          // Better a flow the provider may refuse than a button that silently
          // does nothing — the user can at least see what happened.
          logger.warn(`No shell took the authorization URL (${context}); navigating`, {
            component: 'safe-navigation',
            context,
          });
          window.location.href = url;
        }
      });
    return;
  }

  window.location.href = url;
}
