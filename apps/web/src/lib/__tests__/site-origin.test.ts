/**
 * Canonical site origin resolution (B03 — host-neutral release artifact).
 *
 * What must hold:
 * - APP_URL_SERVER (runtime) wins over NEXT_PUBLIC_APP_URL (optional build
 *   input for the hosted site); with neither, the origin is null — never a
 *   hardcoded deployment hostname;
 * - only absolute HTTP(S) origins pass: credentials, query, fragment, or a
 *   non-root path are rejected loudly (a misconfigured origin must not
 *   silently poison every canonical URL);
 * - localizedUrl builds the exact historical URL shape (no trailing slash on
 *   the bare origin, fr unprefixed, other locales prefixed) and degrades to
 *   RELATIVE paths when no origin is configured.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildAbsoluteUrl,
  getSiteOrigin,
  localizedUrl,
} from '@/lib/site-origin';

describe('getSiteOrigin', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns null when nothing is configured (generic image)', () => {
    vi.stubEnv('APP_URL_SERVER', '');
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '');
    expect(getSiteOrigin()).toBeNull();
  });

  it('prefers the runtime APP_URL_SERVER over the build value', () => {
    vi.stubEnv('APP_URL_SERVER', 'https://lan.example:3000');
    vi.stubEnv('NEXT_PUBLIC_APP_URL', 'https://build.example');
    expect(getSiteOrigin()).toBe('https://lan.example:3000');
  });

  it('accepts LAN http and proxy https origins', () => {
    vi.stubEnv('APP_URL_SERVER', 'http://192.168.1.50:3000');
    expect(getSiteOrigin()).toBe('http://192.168.1.50:3000');
    vi.stubEnv('APP_URL_SERVER', 'https://lia.mydomain.tld');
    expect(getSiteOrigin()).toBe('https://lia.mydomain.tld');
  });

  it.each([
    'ftp://x.example',
    'https://user:pw@x.example',
    'https://x.example/?q=1',
    'https://x.example/#frag',
    'https://x.example/sub/path',
    'not-a-url',
  ])('rejects invalid origin %s loudly', (bad) => {
    vi.stubEnv('APP_URL_SERVER', bad);
    expect(() => getSiteOrigin()).toThrow(/APP_URL_SERVER/);
  });

  it('tolerates a single trailing slash on the origin', () => {
    vi.stubEnv('APP_URL_SERVER', 'https://x.example/');
    expect(getSiteOrigin()).toBe('https://x.example');
  });
});

describe('URL builders', () => {
  it('buildAbsoluteUrl concatenates origin and path without double slash', () => {
    expect(buildAbsoluteUrl('https://x.example', '/demo')).toBe(
      'https://x.example/demo'
    );
    expect(buildAbsoluteUrl('https://x.example', '')).toBe('https://x.example');
  });

  it('localizedUrl keeps the historical shape with an origin', () => {
    expect(localizedUrl('https://x.example', '/demo', 'fr')).toBe(
      'https://x.example/demo'
    );
    expect(localizedUrl('https://x.example', '/demo', 'en')).toBe(
      'https://x.example/en/demo'
    );
    expect(localizedUrl('https://x.example', '', 'fr')).toBe(
      'https://x.example'
    );
  });

  it('localizedUrl degrades to relative paths without an origin', () => {
    expect(localizedUrl(null, '/demo', 'fr')).toBe('/demo');
    expect(localizedUrl(null, '/demo', 'zh')).toBe('/zh/demo');
    expect(localizedUrl(null, '', 'fr')).toBe('/');
  });
});
