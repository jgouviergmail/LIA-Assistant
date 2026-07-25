/**
 * i18n middleware — the language every request is served in.
 *
 * It runs before every page, and its priority order is a product decision:
 * an explicit choice (the `NEXT_LOCALE` cookie set by the language selector)
 * outranks the browser's `Accept-Language`, which only ever decides a first
 * visit. Getting that backwards means a user who picked English keeps landing
 * on French pages — silent, and invisible to any test that only renders
 * components.
 *
 * The second contract is the redirect: `next-i18n-router` answers 307, and the
 * middleware upgrades it to a 301 so Google consolidates ranking signals onto
 * one URL, carrying over any cookie the router set.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { NextRequest, NextResponse } from 'next/server';

// The real router decides every case below; only the two tests that need a
// controlled upstream response (the 307 → 301 upgrade branch) swap it out.
const { override } = vi.hoisted(() => ({
  override: { fn: null as null | (() => NextResponse) },
}));
vi.mock('next-i18n-router', async importOriginal => {
  const actual = await importOriginal<typeof import('next-i18n-router')>();
  return {
    ...actual,
    i18nRouter: (...args: Parameters<typeof actual.i18nRouter>) =>
      override.fn ? override.fn() : actual.i18nRouter(...args),
  };
});

import { proxy, config } from '@/proxy';
import { cookieName, fallbackLng, languages } from '@/i18n/settings';

afterEach(() => {
  override.fn = null;
});

const ORIGIN = 'https://lia.test';

function request(
  path: string,
  { cookie, acceptLanguage }: { cookie?: string; acceptLanguage?: string } = {}
): NextRequest {
  const headers = new Headers();
  if (acceptLanguage) headers.set('Accept-Language', acceptLanguage);
  if (cookie) headers.set('cookie', `${cookieName}=${cookie}`);
  return new NextRequest(new URL(path, ORIGIN), { headers });
}

/** Path the middleware sends the browser to, or null when it serves in place. */
function redirectPath(response: Response): string | null {
  const location = response.headers.get('location');
  return location ? new URL(location, ORIGIN).pathname : null;
}

describe('language detection priority', () => {
  it('honours the cookie the language selector set, ignoring the browser', () => {
    const response = proxy(request('/', { cookie: 'de', acceptLanguage: 'en-US,en;q=0.9' }));
    expect(redirectPath(response)).toBe('/de');
  });

  it('falls through to Accept-Language when the cookie holds an unsupported value', () => {
    const response = proxy(request('/', { cookie: 'pt-BR', acceptLanguage: 'it-IT,it;q=0.9' }));
    expect(redirectPath(response)).toBe('/it');
  });

  it('picks the highest quality factor among supported languages', () => {
    // German is offered last but wins on q; the unsupported ones are skipped.
    const response = proxy(request('/', { acceptLanguage: 'pt;q=0.9,ru;q=0.8,de;q=0.95' }));
    expect(redirectPath(response)).toBe('/de');
  });

  it('treats a segment with no q as the highest priority (RFC 7231 default)', () => {
    const response = proxy(request('/', { acceptLanguage: 'es-ES,de;q=0.9' }));
    expect(redirectPath(response)).toBe('/es');
  });

  it('matches on the base language of a regional tag', () => {
    // The frontend locale is `zh`, never `zh-CN` — that code is the backend's.
    const response = proxy(request('/', { acceptLanguage: 'zh-CN,zh;q=0.9' }));
    expect(redirectPath(response)).toBe('/zh');
  });

  it('serves the fallback language when nothing is negotiable', () => {
    expect(redirectPath(proxy(request('/', { acceptLanguage: 'pt-BR,ru;q=0.8' })))).toBeNull();
    expect(redirectPath(proxy(request('/')))).toBeNull();
  });

  it('ignores a malformed quality factor rather than dropping the language', () => {
    const response = proxy(request('/', { acceptLanguage: 'de;q=abc' }));
    expect(redirectPath(response)).toBe('/de');
  });
});

describe('URL shape', () => {
  it('leaves the default language unprefixed', () => {
    // prefixDefault: false — `/dashboard` IS the French dashboard.
    expect(redirectPath(proxy(request('/dashboard', { cookie: fallbackLng })))).toBeNull();
  });

  it('leaves an already localized path alone', () => {
    expect(redirectPath(proxy(request('/en/dashboard', { cookie: 'en' })))).toBeNull();
  });

  it('keeps the path when redirecting to a prefixed language', () => {
    expect(redirectPath(proxy(request('/dashboard/chat', { cookie: 'en' })))).toBe(
      '/en/dashboard/chat'
    );
  });
});

describe('redirect status', () => {
  it('answers 301, not the router default of 307', () => {
    const response = proxy(request('/', { cookie: 'en' }));
    expect(response.status).toBe(301);
  });

  it('carries a cookie the router set over to the rebuilt 301', () => {
    // The real router sets none today, so the preservation branch is driven
    // with a controlled 307 — otherwise the assertion would be vacuous.
    override.fn = () => {
      const routed = NextResponse.redirect(new URL('/en', ORIGIN));
      routed.cookies.set(cookieName, 'en', { path: '/' });
      return routed;
    };

    const response = proxy(request('/'));

    expect(response.status).toBe(301);
    expect(response.cookies.get(cookieName)?.value).toBe('en');
  });

  it('returns the router response untouched when a 307 carries no location', () => {
    override.fn = () => new NextResponse(null, { status: 307 });

    const response = proxy(request('/'));

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBeNull();
  });

  it('leaves a non-redirect response alone', () => {
    override.fn = () => NextResponse.next({ headers: { 'x-marker': 'kept' } });

    const response = proxy(request('/'));

    expect(response.status).toBe(200);
    expect(response.headers.get('x-marker')).toBe('kept');
  });
});

describe('matcher', () => {
  const matcher = new RegExp(`^${config.matcher}$`);

  it.each(['/', '/dashboard', '/en/dashboard/chat', '/blog/a-post'])('runs on %s', path => {
    expect(matcher.test(path)).toBe(true);
  });

  it.each([
    '/api/v1/chat',
    '/_next/static/chunk.js',
    '/_next/image',
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/llms.txt',
    '/manifest.json',
    '/icon-192.png',
  ])('stays out of %s', path => {
    expect(matcher.test(path)).toBe(false);
  });
});

describe('supported locales', () => {
  it('routes every declared language', () => {
    for (const language of languages) {
      const response = proxy(request('/', { cookie: language }));
      const expected = language === fallbackLng ? null : `/${language}`;
      expect(redirectPath(response)).toBe(expected);
    }
  });
});
