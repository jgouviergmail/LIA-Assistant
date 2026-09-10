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

/**
 * The props an `<img>`/`<video>` needs to display an API resource.
 *
 * Reported from production, 2026-09-10: generated image thumbnails were broken
 * in the chat and in the gallery while opening the same URL showed the image.
 * The web app answers `Cross-Origin-Embedder-Policy: credentialless`, and under
 * that policy a no-CORS cross-origin subresource is fetched WITHOUT
 * credentials — so the session cookie never reached the API and it answered
 * 401. A top-level navigation is not a subresource, which is why the link
 * worked and the defect read as a rendering bug.
 *
 * It became reachable when these resources stopped being relative: a
 * same-origin `<img>` always carries its cookies, and the reverse proxy made
 * every deployment same-origin until {@link apiResourceUrl} started resolving
 * against the API origin.
 *
 * `use-credentials` turns the fetch into a CREDENTIALED CORS request, which the
 * API already answers (`access-control-allow-credentials: true` with the app's
 * origin) and which also satisfies the embedder policy. It is added only when
 * the URL was actually rewritten to another origin: a same-origin resource
 * needs nothing, and a foreign image — a Wikipedia thumbnail, a `data:` or
 * `blob:` URI — would FAIL a credentialed CORS check we have no business
 * asking for.
 *
 * @param wireUrl - What the API sent, or any other image source.
 * @returns Spreadable props: always `src`, plus `crossOrigin` when needed.
 */
export function apiImageProps(wireUrl: string): {
  src: string;
  crossOrigin?: 'use-credentials';
} {
  const src = apiResourceUrl(wireUrl);
  if (src === wireUrl) return { src };
  return { src, crossOrigin: 'use-credentials' };
}
