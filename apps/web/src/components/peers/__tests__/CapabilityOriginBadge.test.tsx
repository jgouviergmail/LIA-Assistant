import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { CapabilityOriginBadge } from '../CapabilityOriginBadge';

vi.unmock('react-i18next');
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'America/New_York' } }),
}));

const origin = {
  sender_display_name: 'Alice',
  shared_at: '2026-10-18T14:30:00Z',
  transfer_id: '11111111-1111-4111-8111-111111111111',
};

describe('CapabilityOriginBadge', () => {
  it.each([
    ['en', /Shared by Alice/],
    ['fr', /Partagé par Alice/],
  ] as const)(
    'has a translated accessible name and the account timezone in %s',
    async (lng, name) => {
      const i18n = createInstance();
      await i18n.init({
        lng,
        interpolation: { escapeValue: false },
        resources: { en: { translation: en }, fr: { translation: fr } },
      });
      render(
        <I18nextProvider i18n={i18n}>
          <CapabilityOriginBadge origin={origin} lng={lng} />
        </I18nextProvider>
      );
      const badge = screen.getByRole('note', { name });
      expect(badge).toHaveTextContent('10:30');
      expect(badge.querySelector('time')).toHaveAttribute('dateTime', origin.shared_at);
    }
  );

  it('renders the sender as plain text, with no image, link or markup', async () => {
    const i18n = createInstance();
    await i18n.init({
      lng: 'en',
      interpolation: { escapeValue: false },
      resources: { en: { translation: en } },
    });
    const sender = '<img src="https://example.test/tracker">';
    render(
      <I18nextProvider i18n={i18n}>
        <CapabilityOriginBadge origin={{ ...origin, sender_display_name: sender }} lng="en" />
      </I18nextProvider>
    );
    expect(screen.getByRole('note')).toHaveTextContent(sender);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('does not invent an origin for missing or malformed data', () => {
    const { rerender } = render(<CapabilityOriginBadge origin={null} lng="en" />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    rerender(<CapabilityOriginBadge origin={{ ...origin, shared_at: 'invalid' }} lng="en" />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});
