/** The language-aware hook reads its provider without loading a second catalogue. */

import { render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { useTranslation as useProviderTranslation } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';

import { ScopedTranslations } from '@/components/ScopedTranslations';
import { TranslationsProvider } from '@/components/TranslationsProvider';
import { translationBundle } from '@/i18n';
import { useTranslation } from '../client';
import { omitTranslations, ROUTE_SCOPED_TRANSLATIONS } from '../scoped-translations';
import { languages, type Language } from '../settings';

vi.unmock('react-i18next');
vi.unmock('@/i18n/client');

function Probe({ lng }: { lng: Language }) {
  const local = useTranslation(lng);
  const parent = useProviderTranslation();
  const prefixed = useTranslation(lng, 'translation', { keyPrefix: 'settings.admin.users' });
  return (
    <p data-testid="probe">
      {String(local.i18n.store === parent.i18n.store)}|{local.i18n.language}|
      {String(local.i18n.hasResourceBundle(local.i18n.language, 'translation'))}|
      {String(local.i18n.exists('settings.admin.users.title'))}|
      {String(local.i18n.exists('more.hero.title'))}|{local.t('settings.admin.users.title')}|
      {prefixed.t('title')}
    </p>
  );
}

function Fixture({
  lng,
  scoped,
  hookLng = lng,
}: {
  lng: Language;
  scoped: boolean;
  hookLng?: Language;
}) {
  const probe = <Probe lng={hookLng} />;
  return (
    <TranslationsProvider
      locale={lng}
      namespaces={['translation']}
      resources={{
        [lng]: { translation: omitTranslations(translationBundle(lng), ROUTE_SCOPED_TRANSLATIONS) },
      }}
    >
      {scoped ? (
        <ScopedTranslations lng={lng} scopes={['settings.admin']}>
          {probe}
        </ScopedTranslations>
      ) : (
        probe
      )}
    </TranslationsProvider>
  );
}

describe('the client translation hook', () => {
  it.each(languages)('%s renders the server locale before a caller language hook settles', lng => {
    const expected = renderToString(<Fixture lng={lng} scoped />);
    const initial = renderToString(<Fixture lng={lng} hookLng="fr" scoped />);
    expect(initial).toBe(expected);
    expect(initial).not.toContain('settings.admin.users.title');
  });

  it.each(languages)('%s keeps t, i18n and keyPrefix on the nearest scope', lng => {
    const { rerender } = render(<Fixture lng={lng} scoped />);
    const probe = screen.getByTestId('probe');
    expect(probe).toHaveTextContent(`true|${lng}|true|true|false|`);
    const parts = probe.textContent?.split('|') ?? [];
    expect(parts[5]).toBe(parts[6]);
    expect(parts[5]).not.toBe('settings.admin.users.title');
    rerender(<Fixture lng={lng} scoped={false} />);
    expect(screen.getByTestId('probe')).toHaveTextContent(
      `true|${lng}|true|false|false|settings.admin.users.title|settings.admin.users.title`
    );
  });

  it('follows a locale navigation without retaining the previous instance', () => {
    const { rerender } = render(<Fixture lng="fr" scoped />);
    const french = screen.getByTestId('probe').textContent;
    rerender(<Fixture lng="de" scoped />);
    expect(screen.getByTestId('probe')).toHaveTextContent('true|de|true|true|false|');
    expect(screen.getByTestId('probe').textContent).not.toBe(french);
    rerender(<Fixture lng="fr" scoped />);
    expect(screen.getByTestId('probe').textContent).toBe(french);
  });
});
