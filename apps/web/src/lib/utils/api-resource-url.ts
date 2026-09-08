/**
 * Absolute URL of an API resource the BROWSER fetches or follows.
 *
 * The API emits resource URLs in their wire form — `/api/v1/attachments/{id}`
 * for a generated document, image or browser screenshot, `/api/v1/connectors/…`
 * for a place photo, a static map or a Drive thumbnail. Left relative, an
 * `<a href>`, an `<img src>` or a `fetch` resolves them against the FRONTEND
 * origin, so they only work where a reverse proxy re-routes `/api/v1/*` to the
 * API. That is the production setup and not the developer one (measured
 * 2026-09-09: the dev API serves HTTPS only, a Next rewrite refuses its
 * self-signed certificate, and every generated document answered 500).
 *
 * This is the rule {@link apiEndpointUrl} already states for links the browser
 * follows; these resources were the last ones not applying it. Both fall back
 * to the relative path when no API origin is configured, so nothing changes
 * for a deployment that does rely on the proxy.
 */

import { apiEndpointUrl } from '@/lib/api-client';

/** The prefix the API puts in front of every wire URL it emits. */
const API_PREFIX = '/api/v1';

/**
 * Resolve an API wire URL against the configured API origin.
 *
 * @param wireUrl - What the API sent, e.g. `/api/v1/attachments/{id}`.
 *   Anything else is returned untouched: an absolute URL (an external image, a
 *   `data:` or `blob:` URI) and any path that is not an API resource. This
 *   function resolves OUR paths and never rewrites somebody else's.
 * @returns The URL the browser should use.
 */
export function apiResourceUrl(wireUrl: string): string {
  if (!wireUrl.startsWith(API_PREFIX)) return wireUrl;
  return apiEndpointUrl(wireUrl.slice(API_PREFIX.length));
}
