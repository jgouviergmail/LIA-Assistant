/** Mounted application routes persist their locale; public pages and SSR do not. */

import { useLayoutEffect } from 'react';
import { renderToString } from 'react-dom/server';
import { render } from '@testing-library/react';
import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApplicationLocaleSync } from '../ApplicationLocaleSync';
import { cookieName, languages, setLocaleCookie, type Language } from '@/i18n/settings';
import { PUBLIC_PAGES } from '@/lib/public-pages';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { proxy } from '@/proxy';

const { usePathname } = vi.hoisted(() => ({ usePathname: vi.fn<() => string>() }));
vi.mock('next/navigation', () => ({ usePathname }));

function savedLocale(): string | undefined {
  return document.cookie
    .split('; ')
    .find(cookie => cookie.startsWith(`${cookieName}=`))
    ?.slice(cookieName.length + 1);
}

/** A later layout effect observes the cookie before passive effects or interactions. */
function MountedRoute({
  locale,
  observe,
}: {
  locale: Language;
  observe: (cookie: string) => void;
}) {
  useLayoutEffect(() => observe(document.cookie), [locale, observe]);
  return <a href={buildLocalizedPath('/dashboard/chat', locale)}>Chat</a>;
}

beforeEach(() => {
  document.cookie = `${cookieName}=; max-age=0; path=/`;
  usePathname.mockReturnValue('/');
});

describe('ApplicationLocaleSync', () => {
  it.each(languages)('leaves the saved preference alone on every public %s page', locale => {
    const saved = locale === 'en' ? 'de' : 'en';
    setLocaleCookie(saved);
    const paths = PUBLIC_PAGES.filter(page => !['/login', '/register'].includes(page.path)).map(
      page => page.path
    );
    paths.push('/blog/google-workspace');
    for (const path of paths) {
      usePathname.mockReturnValue(`/${locale}${path === '/' ? '' : path}`);
      const view = render(<ApplicationLocaleSync locale={locale} />);
      expect(savedLocale(), path).toBe(saved);
      view.unmount();
    }
  });

  it.each(languages)(
    'saves a real %s application entry before the mounted route effects',
    locale => {
      setLocaleCookie(locale === 'en' ? 'de' : 'en');
      usePathname.mockReturnValue(`/${locale}/login`);
      const observe = vi.fn<(cookie: string) => void>();
      render(
        <>
          <ApplicationLocaleSync locale={locale} />
          <MountedRoute locale={locale} observe={observe} />
        </>
      );
      expect(observe).toHaveBeenCalledWith(expect.stringContaining(`${cookieName}=${locale}`));

      // The next existing link uses an unprefixed French path. It must still
      // resolve French, despite the browser's conflicting preferred language.
      const href = `${buildLocalizedPath('/dashboard/chat', locale)}?next=chat`;
      const response = proxy(
        new NextRequest(`https://lia.test${href}`, {
          headers: { cookie: document.cookie, 'Accept-Language': 'en-US' },
        })
      );
      expect(response.headers.get('location')).toBeNull();
      expect(response.headers.get('x-next-i18n-router-locale')).toBe(locale);
      expect(response.cookies.get(cookieName)).toBeUndefined();
      if (locale === 'fr') {
        expect(response.headers.get('x-middleware-rewrite')).toBe(
          'https://lia.test/fr/dashboard/chat?next=chat'
        );
      }
    }
  );

  it('synchronizes an anonymous first application visit without a previous cookie', () => {
    usePathname.mockReturnValue('/fr/dashboard');
    render(<ApplicationLocaleSync locale="fr" />);
    expect(savedLocale()).toBe('fr');
  });

  it('synchronizes actual route changes while public returns preserve the application preference', () => {
    setLocaleCookie('en');
    usePathname.mockReturnValue('/maps');
    const view = render(<ApplicationLocaleSync locale="fr" />);
    expect(savedLocale()).toBe('en');

    // Same provider locale, new pathname: the persistent root must notice it.
    usePathname.mockReturnValue('/fr/login');
    view.rerender(<ApplicationLocaleSync locale="fr" />);
    expect(savedLocale()).toBe('fr');

    usePathname.mockReturnValue('/de/blog');
    view.rerender(<ApplicationLocaleSync locale="de" />);
    expect(savedLocale()).toBe('fr');

    usePathname.mockReturnValue('/de/dashboard');
    view.rerender(<ApplicationLocaleSync locale="de" />);
    expect(savedLocale()).toBe('de');

    usePathname.mockReturnValue('/');
    view.rerender(<ApplicationLocaleSync locale="fr" />);
    expect(savedLocale()).toBe('de');
  });

  it('never writes a cookie while the application component is only server-rendered', () => {
    setLocaleCookie('en');
    usePathname.mockReturnValue('/fr/register');
    expect(renderToString(<ApplicationLocaleSync locale="fr" />)).toBe('');
    expect(savedLocale()).toBe('en');
  });
});
