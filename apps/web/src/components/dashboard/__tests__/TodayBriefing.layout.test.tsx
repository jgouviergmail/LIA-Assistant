/** The independent radio follows the welcome and survives briefing failure. */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseBriefingResult } from '@/hooks/useBriefing';

vi.mock('@/hooks/useBriefingPreferences', () => ({
  useBriefingPreferences: () => ({ preferences: null }),
}));
vi.mock('../HeroLiaCard', () => ({
  HeroLiaCard: ({ children }: { children?: React.ReactNode }) => (
    <section aria-label="hero">{children}</section>
  ),
}));
vi.mock('../DashboardDateHeading', () => ({ DashboardDateHeading: () => <h1>Today</h1> }));
vi.mock('../BriefingSynthesis', () => ({
  BriefingSynthesis: () => <section aria-label="synthesis">The daily point</section>,
}));
vi.mock('../QuickAccessCompact', () => ({
  QuickAccessCompact: () => <nav aria-label="quick access" />,
}));
vi.mock('../PortraitHint', () => ({ PortraitHint: () => null }));
vi.mock('../StarterChecklistCard', () => ({ StarterChecklistCard: () => null }));
vi.mock('@/components/pwa/InstallHint', () => ({ InstallHint: () => null }));
vi.mock('../BriefingError', () => ({
  BriefingError: () => <section aria-label="briefing error" />,
}));

import { TodayBriefing } from '../TodayBriefing';

const LEAD_IN = <section aria-label="radio" />;

const TEXT: UseBriefingResult['text'] = {
  greeting: { text: 'Hello', generated_at: '2026-10-15T08:00:00Z', usage: null },
  synthesis: { text: 'The daily point', generated_at: '2026-10-15T08:00:00Z', usage: null },
};

/** The controller the dashboard hands down: still loading, or failed with nothing to show. */
function briefing({
  failed = false,
  text,
}: { failed?: boolean; text?: UseBriefingResult['text'] } = {}): UseBriefingResult {
  return {
    cards: undefined,
    windows: undefined,
    text,
    loading: !failed,
    cardsLoading: !failed,
    textLoading: !failed,
    textUnavailable: false,
    error: failed ? new Error('down') : null,
    refetchAll: async () => {},
    refetchSection: async () => {},
    invalidateSection: async () => {},
    refreshingSections: new Set(),
  };
}

/** Whether `later` comes after `earlier` in the document. */
function follows(earlier: Element, later: Element): boolean {
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe('TodayBriefing lead-in', () => {
  it('sits once immediately below the welcome, before shortcuts', () => {
    renderWithProviders(<TodayBriefing briefing={briefing()} aboveBriefing={LEAD_IN} />);
    const hero = screen.getByRole('region', { name: 'hero' });
    const quickAccess = screen.getByRole('navigation', { name: 'quick access' });
    const radio = screen.getByRole('region', { name: 'radio' });
    const dashboard = screen.getByRole('heading', { name: 'dashboard.briefing.section_title' });
    expect(screen.getAllByRole('region', { name: 'radio' })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 }).nextElementSibling).toBe(hero);
    expect(hero.nextElementSibling).toBe(radio);
    expect(follows(radio, quickAccess)).toBe(true);
    expect(follows(hero, quickAccess)).toBe(true);
    expect(follows(radio, dashboard)).toBe(true);
  });

  it('stays once below the date when the briefing fails', () => {
    renderWithProviders(
      <TodayBriefing briefing={briefing({ failed: true })} aboveBriefing={LEAD_IN} />
    );
    const quickAccess = screen.getByRole('navigation', { name: 'quick access' });
    const radio = screen.getByRole('region', { name: 'radio' });
    const failure = screen.getByRole('region', { name: 'briefing error' });
    expect(screen.getAllByRole('region', { name: 'radio' })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 }).nextElementSibling).toBe(radio);
    expect(follows(radio, quickAccess)).toBe(true);
    expect(follows(radio, failure)).toBe(true);
  });

  it('preserves the radio node and focus through total failure and recovery', () => {
    const leadIn = (
      <section aria-label="radio">
        <button type="button">Listen</button>
      </section>
    );
    const { rerender } = renderWithProviders(
      <TodayBriefing briefing={briefing()} aboveBriefing={leadIn} />
    );
    const radio = screen.getByRole('region', { name: 'radio' });
    const listen = screen.getByRole('button', { name: 'Listen' });
    listen.focus();
    for (const failed of [true, false]) {
      rerender(<TodayBriefing briefing={briefing({ failed })} aboveBriefing={leadIn} />);
      expect(screen.getAllByRole('region', { name: 'radio' })).toHaveLength(1);
      expect(screen.getByRole('region', { name: 'radio' })).toBe(radio);
      expect(follows(screen.getByRole('heading', { level: 1 }), radio)).toBe(true);
      expect(listen).toHaveFocus();
    }
  });

  it('renders nothing extra when the page gives no lead-in', () => {
    renderWithProviders(<TodayBriefing briefing={briefing()} />);
    expect(screen.queryByRole('region', { name: 'radio' })).not.toBeInTheDocument();
  });

  it('keeps a single synthesis below the dashboard heading even on a refresh error', () => {
    const { rerender } = renderWithProviders(
      <TodayBriefing briefing={briefing({ text: TEXT })} aboveBriefing={LEAD_IN} />
    );
    const point = screen.getByRole('region', { name: 'synthesis' });
    const hero = screen.getByRole('region', { name: 'hero' });
    expect(hero).not.toContainElement(point);
    expect(follows(screen.getByRole('navigation', { name: 'quick access' }), point)).toBe(true);
    expect(
      follows(screen.getByRole('heading', { name: 'dashboard.briefing.section_title' }), point)
    ).toBe(true);
    rerender(
      <TodayBriefing briefing={briefing({ failed: true, text: TEXT })} aboveBriefing={LEAD_IN} />
    );
    expect(screen.getAllByRole('region', { name: 'synthesis' })).toHaveLength(1);
    expect(screen.getByRole('region', { name: 'synthesis' })).toBe(point);
    expect(screen.getByRole('region', { name: 'radio' })).toBeInTheDocument();
  });
});
