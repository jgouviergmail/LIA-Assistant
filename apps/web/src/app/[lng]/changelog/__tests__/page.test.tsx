/**
 * `/changelog` metadata — the half of this page that is not visible.
 *
 * The page exists to be FOUND: it is the destination of "see the full history"
 * on the landing and in both footers, and the only public surface carrying the
 * release history at all (the public FAQ never did). A canonical URL, six
 * hreflang alternates and an x-default are therefore load-bearing, not
 * decoration — and none of them shows up in a render test.
 *
 * Translations are the REAL ones: the page deliberately introduces no i18n key
 * of its own and reuses `faq.changelog.*`, so a test against a stubbed
 * translator would pass even if that reuse silently broke.
 */

import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/changelog/ChangelogHistory', () => ({
  ChangelogHistory: () => <div data-testid="changelog-history" />,
}));
vi.mock('@/components/landing/LandingHeader', () => ({
  LandingHeader: () => <div data-testid="landing-header" />,
}));
vi.mock('@/components/layout/PublicFooter', () => ({
  PublicFooter: () => <div data-testid="public-footer" />,
}));

import ChangelogPage, { generateMetadata } from '../page';

const ORIGIN = 'https://lia.test';

function paramsFor(lng: string) {
  return { params: Promise.resolve({ lng }) };
}

describe('/changelog metadata', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('declares a canonical URL and one alternate per supported locale', async () => {
    vi.stubEnv('NEXT_PUBLIC_APP_URL', ORIGIN);
    vi.stubEnv('APP_URL_SERVER', '');

    const metadata = await generateMetadata(paramsFor('fr'));

    // fr is the default locale — no prefix (prefixDefault: false).
    expect(metadata.alternates?.canonical).toBe(`${ORIGIN}/changelog`);
    expect(metadata.alternates?.languages).toMatchObject({
      fr: `${ORIGIN}/changelog`,
      en: `${ORIGIN}/en/changelog`,
      de: `${ORIGIN}/de/changelog`,
      es: `${ORIGIN}/es/changelog`,
      it: `${ORIGIN}/it/changelog`,
      zh: `${ORIGIN}/zh/changelog`,
      'x-default': `${ORIGIN}/changelog`,
    });
  });

  it('canonicalises a prefixed locale to its own URL, not to the default one', async () => {
    vi.stubEnv('NEXT_PUBLIC_APP_URL', ORIGIN);
    vi.stubEnv('APP_URL_SERVER', '');

    const metadata = await generateMetadata(paramsFor('en'));

    expect(metadata.alternates?.canonical).toBe(`${ORIGIN}/en/changelog`);
    expect(metadata.openGraph?.url).toBe(`${ORIGIN}/en/changelog`);
  });

  it('titles and describes the page with the changelog wording already translated', async () => {
    const metadata = await generateMetadata(paramsFor('fr'));

    // The reuse under test: no `changelog.meta.*` key was invented.
    expect(metadata.title).toContain('Historique des versions');
    expect(metadata.description).toBe('Évolutions fonctionnelles de LIA version par version');
  });

  it('announces the sibling locales to social crawlers', async () => {
    const metadata = await generateMetadata(paramsFor('fr'));

    const openGraph = metadata.openGraph as { locale?: string; alternateLocale?: string[] };
    expect(openGraph.locale).toBeTruthy();
    expect(openGraph.alternateLocale).toHaveLength(5);
    expect(openGraph.alternateLocale).not.toContain(openGraph.locale);
  });

  it('falls back to the default locale rather than trusting the URL segment', async () => {
    const metadata = await generateMetadata(paramsFor('klingon'));

    expect(metadata.title).toContain('Historique des versions');
  });
});

describe('/changelog page', () => {
  it('keeps the sign-up call to action in the language being read', async () => {
    // A visitor reading the history in English must not be dropped on the
    // unprefixed French route by the one CTA the page carries.
    render(await ChangelogPage(paramsFor('en')));

    expect(screen.getByRole('link')).toHaveAttribute('href', '/en/register');
  });

  it('leaves the default locale unprefixed', async () => {
    render(await ChangelogPage(paramsFor('fr')));

    expect(screen.getByRole('link')).toHaveAttribute('href', '/register');
  });

  it('gives the history a level-1 heading of its own', async () => {
    render(await ChangelogPage(paramsFor('fr')));

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Historique des versions');
    expect(screen.getByTestId('changelog-history')).toBeInTheDocument();
  });
});
