/**
 * Route-scoped translations: the root catalogue leaves route-only subtrees out, and a
 * route's scope brings back exactly what it asks for, without re-sending what
 * the root already holds.
 *
 * The real react-i18next runs here (the shared setup echoes keys, which would
 * make a missing subtree indistinguishable from a present one).
 */

import { render, screen } from '@testing-library/react';
import { useTranslation } from 'react-i18next';
import { createInstance } from 'i18next';
import { describe, expect, it, vi } from 'vitest';

import { deepFreeze } from '@/__tests__/deep-freeze';
import { ScopedTranslations } from '@/components/ScopedTranslations';
import { TranslationsProvider } from '@/components/TranslationsProvider';
import { translationBundle } from '@/i18n';
import { languages, type Language } from '@/i18n/settings';
import {
  DASHBOARD_TRANSLATION_SCOPES,
  ROUTE_SCOPED_TRANSLATIONS,
  mergeTranslations,
  omitTranslations,
  pickTranslations,
  scopedTranslationPaths,
} from '../scoped-translations';

vi.unmock('react-i18next');

const TREE = deepFreeze({
  faq: { title: 'FAQ', sections: { a: { title: 'A' }, b: { title: 'B' } }, intro: { x: 'X' } },
  blog: { articles: { one: { title: 'One' } } },
  common: { ok: 'OK' },
});

describe('omitTranslations', () => {
  it('leaves the paths out and shares every branch it does not touch', () => {
    const kept = omitTranslations(TREE, ['faq.sections', 'blog']);
    expect(kept).toEqual({ faq: { title: 'FAQ', intro: { x: 'X' } }, common: { ok: 'OK' } });
    expect(kept.common).toBe(TREE.common);
    expect((kept.faq as typeof TREE.faq).intro).toBe(TREE.faq.intro);
  });

  it('returns the tree itself for paths it does not hold', () => {
    // An absent root, and a present prefix whose leaf is a string, not a subtree.
    expect(omitTranslations(TREE, ['nothing.here', 'common.ok.deeper', 'constructor'])).toBe(TREE);
  });
});

describe('pickTranslations', () => {
  it('keeps the requested subtrees at their place, merged under a shared parent', () => {
    expect(pickTranslations(TREE, ['faq.sections.b', 'faq.intro', 'missing.path'])).toEqual({
      faq: { sections: { b: { title: 'B' } }, intro: { x: 'X' } },
    });
  });
});

describe('mergeTranslations', () => {
  it('merges subtrees key by key and never mutates either side', () => {
    const merged = mergeTranslations(omitTranslations(TREE, ['faq.sections']), {
      faq: { sections: { a: { title: 'A' } } },
    });
    expect(merged).toEqual({
      ...TREE,
      faq: { title: 'FAQ', intro: { x: 'X' }, sections: { a: { title: 'A' } } },
    });
  });
});

describe('scopedTranslationPaths', () => {
  it('stands a whole subtree for itself and a partial one for each requested child', () => {
    expect(
      scopedTranslationPaths(['faq.intro', { root: 'faq.sections', keys: ['a', 'b'] }])
    ).toEqual(['faq.intro', 'faq.sections.a', 'faq.sections.b']);
  });
});

describe('the root catalogue', () => {
  it('leaves out the subtrees only some routes read, and keeps the rest', () => {
    const whole = translationBundle('fr');
    const root = omitTranslations(whole, ROUTE_SCOPED_TRANSLATIONS);
    const faq = root.faq as Record<string, unknown>;
    expect(Object.keys(faq)).not.toContain('sections');
    expect(Object.keys(faq)).not.toContain('changelog');
    expect(Object.keys(faq)).toContain('title');
    expect(root).not.toHaveProperty('blog');
    expect(root.landing).toBe(whole.landing);
    // The point of the cut: most of the catalogue never reaches a page that
    // does not read it (63 % in French when it was made, 2026-10-28).
    expect(JSON.stringify(root).length).toBeLessThan(JSON.stringify(whole).length / 2);
  });

  it.each(languages)('%s keeps application text off public pages without losing it', lng => {
    const whole = translationBundle(lng);
    const previous = omitTranslations(whole, [
      'faq.sections',
      'faq.changelog',
      'faq.intro',
      'blog',
    ]);
    const root = omitTranslations(whole, ROUTE_SCOPED_TRANSLATIONS);
    const dashboard = mergeTranslations(
      root,
      pickTranslations(whole, DASHBOARD_TRANSLATION_SCOPES)
    );
    expect(root).not.toHaveProperty('settings.admin');
    expect(root).not.toHaveProperty('meetings');
    expect(root).not.toHaveProperty('more');
    expect(root).not.toHaveProperty('showroom');
    expect(root).toHaveProperty('settings.language');
    expect(root).toHaveProperty('errors');
    expect(dashboard).toEqual(omitTranslations(previous, ['more', 'showroom']));
    // Measure UTF-8 payload bytes, including languages with multibyte glyphs.
    expect(new TextEncoder().encode(JSON.stringify(root)).length).toBeLessThan(
      new TextEncoder().encode(JSON.stringify(previous)).length * 0.4
    );
  });
});

function Probe({ testId }: { testId: string }) {
  const { t } = useTranslation();
  return (
    <p data-testid={testId}>
      {t('faq.title')}|{t('faq.sections.getting_started.title')}|{t('faq.sections.chat.title')}
    </p>
  );
}

describe('ScopedTranslations', () => {
  it('adds the requested children under its route and nowhere else', () => {
    const whole = translationBundle('fr');
    const sections = (whole.faq as { sections: Record<string, { title: string }> }).sections;
    render(
      <TranslationsProvider
        locale="fr"
        namespaces={['translation']}
        resources={{ fr: { translation: omitTranslations(whole, ROUTE_SCOPED_TRANSLATIONS) } }}
      >
        <Probe testId="outside" />
        <ScopedTranslations lng="fr" scopes={[{ root: 'faq.sections', keys: ['getting_started'] }]}>
          <Probe testId="inside" />
        </ScopedTranslations>
      </TranslationsProvider>
    );

    const title = (whole.faq as { title: string }).title;
    expect(screen.getByTestId('outside')).toHaveTextContent(
      `${title}|faq.sections.getting_started.title|faq.sections.chat.title`
    );
    // Inherited keys still resolve; the requested child is back; the others are not.
    expect(screen.getByTestId('inside')).toHaveTextContent(
      `${title}|${sections.getting_started.title}|faq.sections.chat.title`
    );
  });
});

const NAVIGATION_KEYS = ['common.loading', 'settings.admin.users.title', 'more.hero.title'];

function NavigationProbe({ testId }: { testId: string }) {
  const { t } = useTranslation();
  return <p data-testid={testId}>{NAVIGATION_KEYS.map(key => t(key)).join('|')}</p>;
}

function NavigationFixture({ lng, inDashboard }: { lng: Language; inDashboard: boolean }) {
  return (
    <TranslationsProvider
      locale={lng}
      namespaces={['translation']}
      resources={{
        [lng]: { translation: omitTranslations(translationBundle(lng), ROUTE_SCOPED_TRANSLATIONS) },
      }}
    >
      <NavigationProbe testId="root" />
      <ScopedTranslations lng={lng} scopes={inDashboard ? ['settings.admin'] : ['more']}>
        <NavigationProbe testId="route" />
        <ScopedTranslations lng={lng} scopes={['more']}>
          <NavigationProbe testId="nested" />
        </ScopedTranslations>
      </ScopedTranslations>
      <ScopedTranslations lng={lng} scopes={['more']}>
        <NavigationProbe testId="sibling" />
      </ScopedTranslations>
    </TranslationsProvider>
  );
}

describe('scope navigation with real translations', () => {
  it.each(languages)('%s restores routes without leaking into the root or sibling', async lng => {
    const full = createInstance();
    await full.init({ lng, resources: { [lng]: { translation: translationBundle(lng) } } });
    const [loading, admin, more] = NAVIGATION_KEYS.map(key => full.t(key));
    expect(admin).not.toBe(NAVIGATION_KEYS[1]);
    expect(more).not.toBe(NAVIGATION_KEYS[2]);
    const { rerender } = render(<NavigationFixture lng={lng} inDashboard />);
    expect(screen.getByTestId('root')).toHaveTextContent(
      `${loading}|${NAVIGATION_KEYS[1]}|${NAVIGATION_KEYS[2]}`
    );
    expect(screen.getByTestId('route')).toHaveTextContent(
      `${loading}|${admin}|${NAVIGATION_KEYS[2]}`
    );
    expect(screen.getByTestId('nested')).toHaveTextContent(`${loading}|${admin}|${more}`);
    expect(screen.getByTestId('sibling')).toHaveTextContent(
      `${loading}|${NAVIGATION_KEYS[1]}|${more}`
    );

    rerender(<NavigationFixture lng={lng} inDashboard={false} />);
    expect(screen.getByTestId('route')).toHaveTextContent(
      `${loading}|${NAVIGATION_KEYS[1]}|${more}`
    );
    expect(screen.getByTestId('nested')).toHaveTextContent(
      `${loading}|${NAVIGATION_KEYS[1]}|${more}`
    );

    rerender(<NavigationFixture lng={lng} inDashboard />);
    expect(screen.getByTestId('route')).toHaveTextContent(
      `${loading}|${admin}|${NAVIGATION_KEYS[2]}`
    );
  });
});
