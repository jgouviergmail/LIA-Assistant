import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import { CosmosFinale } from '../CosmosFinale';

// The shared setup normally returns translation keys. These CTA contracts
// exercise the real hook/provider with the actual homepage copy instead.
vi.unmock('react-i18next');

const resources = { en, fr };
const paths = {
  en: { demo: '/en/demo', register: '/en/register', why: '/en/why' },
  fr: { demo: '/demo', register: '/register', why: '/why' },
};

afterEach(() => {
  vi.unstubAllEnvs();
});

describe.each(['en', 'fr'] as const)('CosmosFinale localized actions (%s)', language => {
  it.each(['guided', 'legacy'] as const)(
    'offers truthful destinations and keyboard priority under %s',
    async variant => {
      vi.stubEnv('NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT', variant);
      const i18n = createInstance();
      await i18n.init({
        lng: language,
        resources: { en: { translation: en }, fr: { translation: fr } },
      });
      const copy = resources[language].landing;
      const user = userEvent.setup();
      render(
        <I18nextProvider i18n={i18n}>
          <CosmosFinale lng={language} />
        </I18nextProvider>
      );

      expect(screen.getByRole('heading', { level: 2, name: copy.home_cta.title })).toBeVisible();
      expect(screen.getByText(copy.home_cta.subtitle)).toBeVisible();
      expect(screen.getByText(copy.home_cta.note_beta)).toBeVisible();

      const account = screen.getByRole('link', { name: copy.home_cta.button });
      expect(account).toBeVisible();
      expect(account).toHaveAttribute('href', paths[language].register);
      const install = screen.getByRole('link', { name: copy.home_cta.install_link });
      expect(install).toBeVisible();
      expect(install).toHaveAttribute(
        'href',
        'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/GETTING_STARTED.md'
      );
      expect(install).toHaveAttribute('target', '_blank');
      expect(install).toHaveAttribute('rel', 'noopener noreferrer');
      expect(
        screen.getByRole('link', {
          name: name => name.startsWith(copy.home_cta.philosophy_link),
        })
      ).toHaveAttribute('href', paths[language].why);

      if (variant === 'guided') {
        const demo = screen.getByRole('link', { name: copy.hero.home_cta_demo });
        expect(demo).toBeVisible();
        expect(demo).toHaveAttribute('href', paths[language].demo);
        await user.tab();
        expect(demo).toHaveFocus();
      } else {
        expect(
          screen.queryByRole('link', { name: copy.hero.home_cta_demo })
        ).not.toBeInTheDocument();
        expect(screen.getAllByRole('link').map(link => link.getAttribute('href'))).not.toContain(
          paths[language].demo
        );
      }
      await user.tab();
      expect(account).toHaveFocus();
    }
  );
});
