/**
 * Canonical site origin (B03, ADR-215 — host-neutral release artifact).
 *
 * Resolution order:
 * 1. `APP_URL_SERVER` — runtime, server-only (the self-host installer and
 *    the standalone server set it; also feeds the API rewrite);
 * 2. `NEXT_PUBLIC_APP_URL` — OPTIONAL build input for the hosted site (its
 *    SSG pages evaluate metadata at build time, so a runtime-only origin
 *    would force the whole public surface dynamic);
 * 3. `null` — the generic prebuilt image: canonical/alternate URLs degrade
 *    to RELATIVE paths, JSON-LD is skipped, and the dynamic sitemap/robots
 *    read the runtime value per request. No deployment hostname is ever
 *    hardcoded anywhere.
 *
 * A configured-but-invalid origin throws loudly: silently accepting it
 * would poison every canonical URL of the deployment.
 */

import { fallbackLng } from '@/i18n/settings';

const HTTP_PROTOCOLS = new Set(['http:', 'https:']);

function validateOrigin(raw: string, source: string): string {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(
      `${source} must be an absolute HTTP(S) origin (e.g. https://lia.example.tld)`
    );
  }
  const valid =
    HTTP_PROTOCOLS.has(url.protocol) &&
    url.username === '' &&
    url.password === '' &&
    url.search === '' &&
    url.hash === '' &&
    url.pathname === '/';
  if (!valid) {
    throw new Error(
      `${source} must be a bare HTTP(S) origin — no credentials, path, query, or fragment`
    );
  }
  return url.origin;
}

/** Resolve the deployment's canonical origin, or null when unconfigured. */
export function getSiteOrigin(): string | null {
  const runtime = process.env.APP_URL_SERVER;
  if (runtime) return validateOrigin(runtime, 'APP_URL_SERVER');
  const build = process.env.NEXT_PUBLIC_APP_URL;
  if (build) return validateOrigin(build, 'NEXT_PUBLIC_APP_URL');
  return null;
}

/** Join an origin and an absolute path (empty path → the bare origin). */
export function buildAbsoluteUrl(origin: string, path: string): string {
  return `${origin}${path}`;
}

/**
 * Localized URL in the historical shape: French (default locale) is
 * unprefixed, every other locale is `/{lng}` — absolute when an origin is
 * configured, honest RELATIVE otherwise.
 */
export function localizedUrl(
  origin: string | null,
  path: string,
  lng: string
): string {
  const localizedPath = lng === fallbackLng ? path : `/${lng}${path}`;
  if (origin === null) {
    return localizedPath === '' ? '/' : localizedPath;
  }
  return buildAbsoluteUrl(origin, localizedPath);
}
