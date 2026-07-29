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
import { BRIEFING_SECTION_NAMES } from '@/types/briefing';

const CONTENT: Record<string, string> = {
  'dashboard.briefing.not_configured_intro_one': 'Une carte attend une configuration :',
  'dashboard.briefing.not_configured_intro_other': '{{count}} cartes attendent une configuration :',
  'dashboard.briefing.not_configured_cta': 'Configurer la carte {{card}}',
  // Card titles live under `cards.<section>.title` — the same keys the card
  // headers use. A prior `sections.<section>.title` path existed in no locale
  // and rendered every name as the raw key (guarded below against real JSON).
  'dashboard.briefing.cards.agenda.title': 'Agenda',
  'dashboard.briefing.cards.mails.title': 'Mails',
  'dashboard.briefing.cards.health.title': 'Santé',
  'dashboard.briefing.cards.reminders.title': 'Rappels',
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

/**
 * Guard against the mocked dictionary drifting away from the real contract.
 *
 * The tests above mock `react-i18next`, so a wrong key path (like the shipped
 * `sections.<section>.title`, which existed in no locale) would still render
 * because the mock happens to define that key. This suite reads the REAL locale
 * JSON and pins the exact key the component builds — `cards.<section>.title` —
 * for every briefing section, in every language. If the path drifts again, or a
 * new section lacks a title, it fails here instead of shipping raw keys.
 */
describe('BriefingSetupHint — key path resolves against real locales', () => {
  const LOCALES = ['en', 'fr', 'de', 'es', 'it', 'zh'] as const;
  for (const lng of LOCALES) {
    it(`every card title the hint can render exists in ${lng}`, async () => {
      const bundle = (await import(`../../../../locales/${lng}/translation.json`)).default as Record<
        string,
        unknown
      >;
      const cards = ((bundle.dashboard as Record<string, Record<string, Record<string, unknown>>>)
        ?.briefing?.cards ?? {}) as Record<string, { title?: unknown }>;
      for (const section of BRIEFING_SECTION_NAMES) {
        expect(
          typeof cards[section]?.title === 'string' && (cards[section].title as string).length > 0,
          `dashboard.briefing.cards.${section}.title missing in ${lng}`
        ).toBe(true);
      }
    });
  }
});
