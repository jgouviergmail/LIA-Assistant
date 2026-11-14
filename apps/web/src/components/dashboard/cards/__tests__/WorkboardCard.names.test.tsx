/**
 * WorkboardCard — every label it names exists in the locale files.
 *
 * The card's other tests translate a key into itself, so a key that left the
 * locale files stays green there. It happened: `settings.workboard.*` went
 * away with the board's settings section (2026-11-11) while this card still
 * named five of its keys, and only a type error in a browser journey said so.
 * Here the translator IS the locale file, and a key it does not hold throws.
 */
import { describe, expect, it, vi } from 'vitest';
import { within } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import type { CardSection, WorkboardData, WorkboardTicketItem } from '@/types/briefing';
import { WorkboardCard } from '../WorkboardCard';

const active = vi.hoisted(() => ({ language: 'fr' }));

vi.mock('react-i18next', async () => {
  const locales: Record<string, unknown> = {
    en: (await import('../../../../../locales/en/translation.json')).default,
    fr: (await import('../../../../../locales/fr/translation.json')).default,
  };
  const read = (path: string): unknown =>
    path
      .split('.')
      .reduce<unknown>(
        (node, part) =>
          typeof node === 'object' && node !== null
            ? (node as Record<string, unknown>)[part]
            : undefined,
        locales[active.language]
      );
  const t = (key: string, values: Record<string, unknown> = {}) => {
    const plural = typeof values.count === 'number' ? (values.count === 1 ? '_one' : '_other') : '';
    const value = read(key + plural) ?? read(key);
    if (typeof value !== 'string') throw new Error(`no locale value for « ${key} »`);
    return value.replace(/\{\{(\w+)\}\}/g, (_match, name: string) => String(values[name] ?? ''));
  };
  return {
    useTranslation: () => ({ t, i18n: { language: active.language, changeLanguage: vi.fn() } }),
  };
});

const props = { isRefreshing: false, onRefresh: () => {}, staggerIndex: 0 };

function ticket(over: Partial<WorkboardTicketItem>): WorkboardTicketItem {
  return {
    id: 't-1',
    title: 'Book the venue',
    status: 'waiting',
    due_at: null,
    overdue: false,
    ...over,
  };
}

function section(data: WorkboardData): CardSection<WorkboardData> {
  return {
    status: 'ok',
    data,
    generated_at: '2026-10-03T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

/** Every figure, every group and the « nothing waits » line: all the card can name. */
const WHOLE: WorkboardData = {
  needs_me: 0,
  held_by_me: 4,
  held_by_lia: 2,
  held_by_peers: 1,
  overdue: 3,
  open_total: 12,
  items: [],
  previews: {
    needs_me: [],
    held_by_me: [ticket({ id: 'mine', category: 'Maison' })],
    held_by_lia: [],
    held_by_peers: [],
    overdue: [ticket({ id: 'late', title: 'Renew the passport', overdue: true })],
    open_total: [],
  },
};

describe.each([
  ['fr', fr],
  ['en', en],
] as const)('WorkboardCard — its labels in %s', (language, locale) => {
  it('draws every label from the locale file, and names no key the file does not hold', () => {
    active.language = language;
    // A key the locale does not hold THROWS in the translator above: rendering
    // at all is the first half of the proof.
    renderWithProviders(<WorkboardCard {...props} section={section(WHOLE)} />);

    const summary = locale.workboard.summary;
    const glance = screen.getByRole('list', { name: summary.title });
    for (const label of [summary.tile_mine, summary.tile_lia, summary.tile_overdue]) {
      expect(within(glance).getByRole('link', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getByText(summary.nothing_waiting)).toBeInTheDocument();
    // The late ticket's own badge, not the figure of the same name above it.
    const late = screen.getByRole('link', { name: /Renew the passport/ });
    expect(within(late).getByText(locale.workboard.card.overdue)).toBeInTheDocument();
  });
});
