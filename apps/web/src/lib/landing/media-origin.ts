/**
 * Where the landing's media directory is, read at request time (ADR-330).
 *
 * Server-side only. The pages are prebuilt and host-neutral (B03), so the
 * origin comes from the environment of the RUNNING server, like
 * `APP_URL_SERVER`: `LANDING_MEDIA_BASE_URL`, the absolute URL of a directory
 * holding `manifest.json`. Unset means the landing shows no video.
 *
 * The manifest and the beat map are fetched behind one small cache: one
 * fetch per TTL whatever the traffic, a failure remembered briefly so a down
 * origin is not asked on every page view, and a slow origin cut at the
 * timeout — the landing never waits for its video. The cache is per server
 * process, which is all a web container runs.
 */

import { type LandingMediaManifest, landingMediaManifestSchema } from './media';

export const LANDING_MEDIA_TTL_MS = 5 * 60_000;
export const LANDING_MEDIA_NEGATIVE_TTL_MS = 60_000;
export const LANDING_MEDIA_FETCH_TIMEOUT_MS = 3_000;
export const LANDING_MEDIA_MANIFEST_FILE = 'manifest.json';

type Env = Record<string, string | undefined>;

/**
 * The configured media directory, without its trailing slash, or null.
 *
 * @throws {TypeError} when the variable is set but is not an absolute http(s)
 *   URL without query or fragment — a configured-but-wrong origin must be
 *   seen, not silently read as "no video".
 */
export function landingMediaBaseUrl(env: Env = process.env): string | null {
  const raw = env.LANDING_MEDIA_BASE_URL?.trim();
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new TypeError(
      'LANDING_MEDIA_BASE_URL must be the absolute http(s) URL of the media directory'
    );
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new TypeError('LANDING_MEDIA_BASE_URL must be an http(s) URL');
  }
  if (url.search || url.hash) {
    throw new TypeError('LANDING_MEDIA_BASE_URL names a directory: no query, no fragment');
  }
  return url.toString().replace(/\/+$/, '');
}

interface CacheEntry {
  expiresAt: number;
  value: unknown;
}

const cache = new Map<string, CacheEntry>();

/** Tests only: forget every cached answer. */
export function resetLandingMediaCache(): void {
  cache.clear();
}

async function fetchJson<T>(url: string, parse: (raw: unknown) => T): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), LANDING_MEDIA_FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      cache: 'no-store',
      headers: { accept: 'application/json' },
      signal: controller.signal,
    });
    if (!response.ok) return null;
    return parse(await response.json());
  } catch {
    // A down origin, a timeout, a body that is not what was declared: all
    // read as "no media" for a while. The route says nothing else.
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetch and parse a JSON document, remembering the answer — a value for
 * `LANDING_MEDIA_TTL_MS`, a failure for `LANDING_MEDIA_NEGATIVE_TTL_MS`.
 */
export async function fetchJsonCached<T>(
  url: string,
  parse: (raw: unknown) => T
): Promise<T | null> {
  const now = Date.now();
  const hit = cache.get(url);
  if (hit && hit.expiresAt > now) return hit.value as T | null;
  const value = await fetchJson(url, parse);
  cache.set(url, {
    expiresAt: now + (value === null ? LANDING_MEDIA_NEGATIVE_TTL_MS : LANDING_MEDIA_TTL_MS),
    value,
  });
  return value;
}

/**
 * The configured directory and its validated manifest, or null when there is
 * no video to show (nothing configured, origin down, manifest invalid).
 *
 * @throws {TypeError} when `LANDING_MEDIA_BASE_URL` is malformed.
 */
export async function loadLandingManifest(): Promise<{
  baseUrl: string;
  manifest: LandingMediaManifest;
} | null> {
  const baseUrl = landingMediaBaseUrl();
  if (!baseUrl) return null;
  const manifest = await fetchJsonCached(`${baseUrl}/${LANDING_MEDIA_MANIFEST_FILE}`, raw =>
    landingMediaManifestSchema.parse(raw)
  );
  return manifest ? { baseUrl, manifest } : null;
}
