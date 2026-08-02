'use client';

/**
 * Opening the chat with a one-shot request — a REAL navigation, never a push.
 *
 * A chat deep link (`?intent=`, `?draft=`, `?voice=`) is not a view
 * transition: it is a request that must arrive exactly as it was built. On
 * 2026-08-01 production proved that `router.push` cannot promise that.
 *
 * **What was measured** (hermetic browser run, production bundle). The App
 * Router restores the search params of the entry it already holds for a route.
 * A click that pushed `/dashboard/chat?draft=…Paul Martin…` landed on
 * `/dashboard/chat?intent=…Marie Dupont…&subject=Marie Dupont` — a URL the
 * application cannot build (`chatIntentHref` is a pure function of its
 * arguments). The first 360° of a session therefore replayed itself for every
 * later deep link: four identical rows in `conversation_messages`, and three
 * semantic-pivot cache HITS, which only happen when the very same string
 * arrives at the backend.
 *
 * Three candidate causes were ruled out by experiment, not by reasoning:
 *
 * - static prerendering — the route was forced dynamic, the defect was
 *   unchanged;
 * - our own one-shot URL cleanup — a first visit carrying no query, hence no
 *   cleanup at all, still poisoned the next deep link;
 * - the i18n rewrite of the default locale — identical in `en`, where the URL
 *   already carries its locale and no rewrite applies.
 *
 * What remains is the router's own bookkeeping, which the application cannot
 * correct from the outside. So it stops depending on it: a real navigation
 * makes the BROWSER the single authority on the URL, and the chat page boots
 * from the address bar rather than from a cache entry.
 *
 * The prefill case is the dangerous one, and the reason this is uniform rather
 * than reserved for auto-sent intents: a `?draft=` link returning as a stale
 * `?intent=` does not merely show the wrong text — it EXECUTES a request the
 * user never made on that click.
 *
 * Cost, measured on the production bundle: ~155 ms and one shell repaint per
 * deep link (108–214 ms across runs), against an SPA push. External arrivals
 * — notifications, mailed links — already pay it.
 *
 * @see apps/web/e2e/smoke/chat-360-two-people.spec.ts — the browser proof.
 */

import { logger } from '@/lib/logger';

/**
 * Whether this href is an internal path, and therefore ours to navigate to.
 *
 * `window.location.assign` is a navigation PRIMITIVE: handed an absolute URL it
 * leaves the origin, and handed `javascript:` it executes in ours. Every caller
 * today passes `chatIntentHref`/`chatDraftHref`, which can only produce
 * `/{lng}/dashboard/chat…` — this keeps that true for the next caller, rather
 * than relying on each one remembering (same doctrine as `safe-navigation.ts`,
 * which guards the outbound half of the same primitive).
 *
 * Rejected shapes, each a real bypass of a naive `startsWith('/')`:
 * `//host` (protocol-relative — the browser reads it as an absolute URL) and
 * `/\host` (browsers normalise the backslash to a slash, giving the same).
 *
 * @param href - Candidate href.
 * @returns True when the href addresses this application and nothing else.
 */
function isInternalPath(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//') && !href.startsWith('/\\');
}

/**
 * Navigate to a chat deep link the way the browser understands it.
 *
 * @param href - A localized chat URL from `chatIntentHref` / `chatDraftHref`.
 *   Pass the href verbatim: anything appended afterwards would not be covered
 *   by the guarantee this function exists to provide. A non-internal href is
 *   refused and logged rather than followed — reaching this line with one is a
 *   programming error, and navigating away would be the harmful reading of it.
 */
export function openChatDeepLink(href: string): void {
  if (!isInternalPath(href)) {
    logger.error('Refused a chat deep link that is not an internal path', undefined, {
      component: 'chat-deep-link',
      href: href.slice(0, 200),
    });
    return;
  }
  window.location.assign(href);
}
