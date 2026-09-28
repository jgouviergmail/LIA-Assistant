/**
 * Where the home page's lead-in sits (ADR-324 decision 30, owner request
 * 2026-09-27): under the quick-access bar, right above « My dashboard » — never
 * above the hero — and there too when the briefing fails, since what it carries
 * (the radio) does not depend on the briefing.
 */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const briefing = vi.hoisted(() => ({ failed: false }));
vi.mock('@/hooks/useBriefing', () => ({
  useBriefing: () => ({
    cards: null,
    windows: null,
    text: null,
    cardsLoading: !briefing.failed,
    textLoading: !briefing.failed,
    error: briefing.failed ? new Error('down') : null,
    refetchAll: vi.fn(),
    refetchSection: vi.fn(),
    refreshingSections: new Set(),
  }),
}));
vi.mock('@/hooks/useBriefingPreferences', () => ({
  useBriefingPreferences: () => ({ preferences: null }),
}));
vi.mock('../HeroLiaCard', () => ({ HeroLiaCard: () => <section aria-label="hero" /> }));
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

/** Whether `later` comes after `earlier` in the document. */
function follows(earlier: Element, later: Element): boolean {
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe('TodayBriefing lead-in', () => {
  it('sits under the quick-access bar, right above « My dashboard », below the hero', () => {
    briefing.failed = false;
    renderWithProviders(<TodayBriefing aboveBriefing={LEAD_IN} />);
    const hero = screen.getByRole('region', { name: 'hero' });
    const quickAccess = screen.getByRole('navigation', { name: 'quick access' });
    const radio = screen.getByRole('region', { name: 'radio' });
    const dashboard = screen.getByRole('heading', { name: 'dashboard.briefing.section_title' });
    expect(follows(hero, quickAccess)).toBe(true);
    expect(follows(quickAccess, radio)).toBe(true);
    expect(follows(radio, dashboard)).toBe(true);
  });

  it('stays under the quick-access bar when the briefing fails', () => {
    briefing.failed = true;
    renderWithProviders(<TodayBriefing aboveBriefing={LEAD_IN} />);
    const quickAccess = screen.getByRole('navigation', { name: 'quick access' });
    const radio = screen.getByRole('region', { name: 'radio' });
    const failure = screen.getByRole('region', { name: 'briefing error' });
    expect(follows(quickAccess, radio)).toBe(true);
    expect(follows(radio, failure)).toBe(true);
  });

  it('renders nothing extra when the page gives no lead-in', () => {
    briefing.failed = false;
    renderWithProviders(<TodayBriefing />);
    expect(screen.queryByRole('region', { name: 'radio' })).not.toBeInTheDocument();
  });
});
