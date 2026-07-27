/**
 * BriefingSetupHint (W7) — the line that names the invisible holes.
 *
 * What must hold, in order of consequence:
 *  1. nothing is rendered when nothing is missing (no empty container, no
 *     reserved space, no nagging on a fully configured account);
 *  2. each named card links to the settings section that actually configures
 *     it — the health card is gated by a toggle, not by a connector, and
 *     sending its owner to the connectors page would be a dead end;
 *  3. the link carries an accessible name that says what following it does:
 *     "Agenda" alone tells a screen-reader user nothing.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const CONTENT: Record<string, string> = {
  'dashboard.briefing.not_configured_intro_one': 'Une carte attend une configuration :',
  'dashboard.briefing.not_configured_intro_other': '{{count}} cartes attendent une configuration :',
  'dashboard.briefing.not_configured_cta': 'Configurer la carte {{card}}',
  'dashboard.briefing.sections.agenda.title': 'Agenda',
  'dashboard.briefing.sections.mails.title': 'Mails',
  'dashboard.briefing.sections.health.title': 'Santé',
  'dashboard.briefing.sections.reminders.title': 'Rappels',
};

const { translate } = vi.hoisted(() => ({
  translate: (key: string, params?: Record<string, unknown>) => {
    // Mirror i18next plural resolution: the component calls the base key and
    // the library appends the suffix.
    const count = params?.count;
    const resolved = typeof count === 'number' ? `${key}_${count === 1 ? 'one' : 'other'}` : key;
    const dictionary: Record<string, string> = CONTENT;
    const value = resolved in dictionary ? dictionary[resolved] : (dictionary[key] ?? key);
    return params
      ? value.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(params[name] ?? ''))
      : value;
  },
}));

vi.mock('react-i18next', async importOriginal => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: translate,
      i18n: { language: 'fr', changeLanguage: vi.fn() },
    }),
  };
});

import { BriefingSetupHint } from '../BriefingSetupHint';

describe('BriefingSetupHint', () => {
  it('renders nothing when every card is configured', () => {
    const { container } = renderWithProviders(<BriefingSetupHint cards={[]} lng="fr" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names a single missing card', () => {
    renderWithProviders(
      <BriefingSetupHint cards={[{ section: 'agenda', target: 'connectors' }]} lng="fr" />
    );
    expect(screen.getByText('Une carte attend une configuration :')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Configurer la carte Agenda/ })).toBeInTheDocument();
  });

  it('counts and names several missing cards', () => {
    renderWithProviders(
      <BriefingSetupHint
        cards={[
          { section: 'agenda', target: 'connectors' },
          { section: 'mails', target: 'connectors' },
          { section: 'health', target: 'health-metrics' },
        ]}
        lng="fr"
      />
    );
    expect(screen.getByText('3 cartes attendent une configuration :')).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(3);
  });

  it('sends each card to the settings section that really configures it', () => {
    renderWithProviders(
      <BriefingSetupHint
        cards={[
          { section: 'agenda', target: 'connectors' },
          { section: 'health', target: 'health-metrics' },
        ]}
        lng="fr"
      />
    );
    expect(screen.getByRole('link', { name: /Agenda/ })).toHaveAttribute(
      'href',
      '/fr/dashboard/settings?section=connectors'
    );
    // A toggle, not a connector: the connectors page would be a dead end.
    expect(screen.getByRole('link', { name: /Santé/ })).toHaveAttribute(
      'href',
      '/fr/dashboard/settings?section=health-metrics'
    );
  });

  it('honours the current locale in the links', () => {
    renderWithProviders(
      <BriefingSetupHint cards={[{ section: 'agenda', target: 'connectors' }]} lng="de" />
    );
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      '/de/dashboard/settings?section=connectors'
    );
  });

  it('names a card without a destination but never fakes a link', () => {
    renderWithProviders(
      <BriefingSetupHint cards={[{ section: 'reminders', target: null }]} lng="fr" />
    );
    expect(screen.getByText('Rappels')).toBeInTheDocument();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('keeps the separators out of the accessible text', () => {
    // The "·" is decoration; a screen reader announcing "Agenda middle dot
    // Mails" would be noise.
    const { container } = renderWithProviders(
      <BriefingSetupHint
        cards={[
          { section: 'agenda', target: 'connectors' },
          { section: 'mails', target: 'connectors' },
        ]}
        lng="fr"
      />
    );
    const separators = container.querySelectorAll('[aria-hidden="true"]');
    expect(separators.length).toBeGreaterThan(0);
    for (const separator of separators) {
      expect(separator.getAttribute('aria-hidden')).toBe('true');
    }
  });
});
