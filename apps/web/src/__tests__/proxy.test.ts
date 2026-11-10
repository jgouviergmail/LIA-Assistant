/**
 * Public URLs keep their declared language, independently of visitor preferences.
 * Application routes still negotiate the saved language before the browser's.
 * Every case runs the real next-i18n-router, including its cookie handling.
 */

import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';

import { proxy, config } from '@/proxy';
import { cookieName, fallbackLng, languages } from '@/i18n/settings';
import { PUBLIC_PAGES } from '@/lib/public-pages';

const ORIGIN = 'https://lia.test';

function request(
  path: string,
  {
    cookie,
    acceptLanguage,
    headers: extraHeaders,
  }: { cookie?: string; acceptLanguage?: string; headers?: Record<string, string> } = {}
): NextRequest {
  const headers = new Headers(extraHeaders);
  if (acceptLanguage) headers.set('Accept-Language', acceptLanguage);
  if (cookie) headers.set('cookie', `${cookieName}=${cookie}; session=preserved`);
  return new NextRequest(new URL(path, ORIGIN), { headers });
}

/** Path and query the browser is sent to, or null when the URL stays put. */
function redirectPath(response: Response): string | null {
  const location = response.headers.get('location');
  if (!location) return null;
  const url = new URL(location, ORIGIN);
  return `${url.pathname}${url.search}`;
}

const editorialPaths = [
  ...PUBLIC_PAGES.map(page => page.path).filter(path => path !== '/login' && path !== '/register'),
  '/blog/google-workspace',
];

const prefetchHeaders: Record<string, string>[] = [
  { 'next-router-prefetch': '1' },
  { 'next-router-prefetch': '2' },
  { 'next-router-prefetch': '3' },
  { purpose: 'prefetch' },
  { 'sec-purpose': 'prefetch' },
  { 'sec-purpose': 'prefetch;prerender' },
];

describe('public URLs declare their language', () => {
  it.each(languages)('keeps French URLs stable with %s preferences', preferred => {
    for (const path of editorialPaths) {
      const response = proxy(
        request(path, { cookie: preferred, acceptLanguage: `${preferred};q=1,en;q=0.9` })
      );

      expect(redirectPath(response), path).toBeNull();
      expect(response.headers.get('x-next-i18n-router-locale'), path).toBe(fallbackLng);
      expect(response.headers.get('x-middleware-rewrite'), path).toBe(
        `${ORIGIN}/${fallbackLng}${path === '/' ? '' : path}`
      );
      expect(response.cookies.get(cookieName), path).toBeUndefined();
    }
  });

  it.each(languages)('ignores browser negotiation on a first visit in %s', preferred => {
    const response = proxy(request('/how', { acceptLanguage: preferred }));
    expect(redirectPath(response)).toBeNull();
    expect(response.headers.get('x-next-i18n-router-locale')).toBe(fallbackLng);
  });

  it.each(languages)('serves explicit %s URLs even with a conflicting preference', locale => {
    for (const path of editorialPaths) {
      const prefixed = `/${locale}${path === '/' ? '' : path}`;
      const response = proxy(
        request(prefixed, {
          cookie: locale === 'en' ? 'de' : 'en',
          acceptLanguage: 'de-DE,de;q=0.9',
        })
      );

      expect(redirectPath(response), prefixed).toBe(locale === fallbackLng ? path : null);
      expect(response.status, prefixed).toBe(locale === fallbackLng ? 301 : 200);
      expect(response.headers.get('x-next-i18n-router-locale'), prefixed).toBe(locale);
      expect(response.cookies.get(cookieName), prefixed).toBeUndefined();
    }
  });

  it('preserves query parameters and session cookies while rewriting the French URL', () => {
    const incoming = request('/blog/google-workspace?ref=demo&topic=mail', { cookie: 'en' });
    const response = proxy(incoming);

    expect(response.headers.get('x-middleware-rewrite')).toBe(
      `${ORIGIN}/fr/blog/google-workspace?ref=demo&topic=mail`
    );
    expect(response.headers.get('x-middleware-request-cookie')).toContain('session=preserved');
    expect(incoming.cookies.get(cookieName)?.value).toBe('en');
  });

  it('preserves query parameters when permanently normalizing a French prefix', () => {
    const response = proxy(request('/fr/maps/history?month=2026-11', { cookie: 'en' }));

    expect(response.status).toBe(301);
    expect(redirectPath(response)).toBe('/maps/history?month=2026-11');
  });

  it('does not classify an unrelated path by an editorial prefix', () => {
    const response = proxy(request('/blogger', { cookie: 'en' }));
    expect(redirectPath(response)).toBe('/en/blogger');
    expect(response.status).toBe(307);
  });
});

describe('application language negotiation', () => {
  it('honours the cookie the language selector set, ignoring the browser', () => {
    const response = proxy(request('/dashboard', { cookie: 'de', acceptLanguage: 'en-US' }));
    expect(redirectPath(response)).toBe('/de/dashboard');
    expect(response.status).toBe(307);
  });

  it.each(['/login', '/register', '/forgot-password', '/dashboard/chat'])(
    'keeps preference-based redirects temporary for %s',
    path => {
      const response = proxy(request(`${path}?next=chat`, { cookie: 'en' }));
      expect(redirectPath(response)).toBe(`/en${path}?next=chat`);
      expect(response.status).toBe(307);
    }
  );

  it('falls through to Accept-Language when the cookie is unsupported', () => {
    const response = proxy(request('/login', { cookie: 'pt-BR', acceptLanguage: 'it-IT' }));
    expect(redirectPath(response)).toBe('/it/login');
  });

  it.each([
    ['pt;q=0.9,ru;q=0.8,de;q=0.95', 'de'],
    ['es-ES,de;q=0.9', 'es'],
    ['zh-CN,zh;q=0.9', 'zh'],
    ['de;q=abc', 'de'],
  ])('negotiates browser languages %s', (acceptLanguage, expected) => {
    expect(redirectPath(proxy(request('/login', { acceptLanguage })))).toBe(`/${expected}/login`);
  });

  it('serves the fallback when nothing is negotiable', () => {
    expect(redirectPath(proxy(request('/login', { acceptLanguage: 'pt-BR,ru;q=0.8' })))).toBeNull();
    expect(redirectPath(proxy(request('/login')))).toBeNull();
  });

  it.each(languages)('continues routing application requests in %s', language => {
    const response = proxy(request('/dashboard/chat', { cookie: language }));
    expect(redirectPath(response)).toBe(
      language === fallbackLng ? null : `/${language}/dashboard/chat`
    );
  });

  it('keeps an explicit application locale without replacing the saved preference', () => {
    const incoming = request('/en/dashboard?next=chat', { cookie: 'de' });
    const response = proxy(incoming);
    expect(redirectPath(response)).toBeNull();
    expect(response.headers.get('x-next-i18n-router-locale')).toBe('en');
    expect(response.cookies.get(cookieName)).toBeUndefined();
    expect(response.headers.get('x-middleware-request-cookie')).toContain(`${cookieName}=de`);
    expect(incoming.nextUrl.search).toBe('?next=chat');
  });

  it.each(['/fr/login', '/fr/dashboard', '/fr/dashboard/chat'])(
    'serves the explicitly French application URL %s without negotiating again',
    path => {
      for (const cookie of ['de', 'en']) {
        const incoming = request(`${path}?next=chat`, { cookie, acceptLanguage: 'en-US' });
        const response = proxy(incoming);
        expect(response.status).toBe(200);
        expect(redirectPath(response)).toBeNull();
        expect(response.headers.get('x-middleware-rewrite')).toBeNull();
        expect(response.headers.get('x-next-i18n-router-locale')).toBe('fr');
        expect(response.cookies.get(cookieName)).toBeUndefined();
        expect(response.headers.get('x-middleware-request-cookie')).toContain(
          `${cookieName}=${cookie}`
        );
        expect(incoming.nextUrl.pathname).toBe(path);
        expect(incoming.nextUrl.search).toBe('?next=chat');
      }
    }
  );
});

describe('speculative requests never change language preferences', () => {
  it.each(languages)('prefetches %s application links without saving their language', language => {
    for (const path of ['/login', '/register', '/dashboard/chat']) {
      const incoming = request(`/${language}${path}?next=chat`, {
        cookie: language === 'en' ? 'de' : 'en',
        headers: { RSC: '1', 'next-router-prefetch': '1' },
      });
      const response = proxy(incoming);

      expect(response.cookies.get(cookieName), path).toBeUndefined();
      expect(response.status, path).toBe(200);
      expect(redirectPath(response), path).toBeNull();
      expect(response.headers.get('x-next-i18n-router-locale'), path).toBe(language);
      expect(incoming.cookies.get('session')?.value, path).toBe('preserved');

      // Next's adapter strips Flight headers before calling the proxy. The
      // result must be identical when no prefetch marker reaches our code.
      const normalized = proxy(
        request(`/${language}${path}?next=chat`, {
          cookie: language === 'en' ? 'de' : 'en',
        })
      );
      expect(normalized.status, path).toBe(response.status);
      expect(redirectPath(normalized), path).toBe(redirectPath(response));
      expect(normalized.headers.get('x-next-i18n-router-locale'), path).toBe(language);
      expect(normalized.cookies.get(cookieName), path).toBeUndefined();
    }
  });

  it.each(prefetchHeaders)(
    'does not create a preference for a first-visit prefetch with %j',
    headers => {
      const response = proxy(request('/en/login', { headers }));
      expect(redirectPath(response)).toBeNull();
      expect(response.cookies.get(cookieName)).toBeUndefined();
    }
  );

  it('still negotiates an unprefixed login prefetch from the saved preference', () => {
    const response = proxy(
      request('/login?next=chat', {
        cookie: 'de',
        acceptLanguage: 'en-US',
        headers: { 'next-router-prefetch': '1' },
      })
    );
    expect(redirectPath(response)).toBe('/de/login?next=chat');
    expect(response.status).toBe(307);
    expect(response.cookies.get(cookieName)).toBeUndefined();
  });

  it.each(['/en/login', '/en/register', '/en/dashboard/chat'])(
    'preserves the saved preference on a real client navigation to %s',
    path => {
      const incoming = request(`${path}?next=chat`, { cookie: 'de', headers: { RSC: '1' } });
      const response = proxy(incoming);
      expect(redirectPath(response)).toBeNull();
      expect(response.headers.get('x-next-i18n-router-locale')).toBe('en');
      expect(response.cookies.get(cookieName)).toBeUndefined();
      expect(response.headers.get('x-middleware-request-cookie')).toContain(`${cookieName}=de`);
      expect(response.headers.get('x-middleware-request-cookie')).toContain('session=preserved');
      expect(incoming.nextUrl.search).toBe('?next=chat');
    }
  );
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
