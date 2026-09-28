/**
 * The home page's composition: the radio is handed to the briefing's lead-in
 * slot — under the quick-access bar, right above « My dashboard » (owner
 * request, 2026-09-27) — once, and the page keeps its order below it.
 */

import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { is_active: true }, isLoading: false }),
}));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: null }) }));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'fr' }));
vi.mock('@/hooks/usePersonalResults', () => ({
  usePersonalResults: () => ({ results: null, firstLoad: false, error: null }),
}));
vi.mock('@/components/dashboard/TodayBriefing', () => ({
  TodayBriefing: ({ aboveBriefing }: { aboveBriefing?: ReactNode }) => (
    <section aria-label="briefing">{aboveBriefing}</section>
  ),
}));
vi.mock('@/components/radio/RadioDashboardCard', () => ({
  RadioDashboardCard: () => <section aria-label="radio" />,
}));
vi.mock('@/components/dashboard/ResultsSummary', () => ({
  ResultsSummary: () => <section aria-label="results" />,
}));
vi.mock('@/components/dashboard/UsageStatistics', () => ({
  UsageStatistics: () => <section aria-label="usage" />,
}));

import DashboardPage from '../page';

describe('the home page', () => {
  it('hands the radio to the briefing’s lead-in slot, once', () => {
    renderWithProviders(<DashboardPage params={Promise.resolve({ lng: 'fr' })} />);
    const briefing = screen.getByRole('region', { name: 'briefing' });
    expect(within(briefing).getByRole('region', { name: 'radio' })).toBeInTheDocument();
    expect(screen.getAllByRole('region', { name: 'radio' })).toHaveLength(1);
  });

  it('keeps the day’s dashboard, the results and the usage in that order', () => {
    renderWithProviders(<DashboardPage params={Promise.resolve({ lng: 'fr' })} />);
    const order = screen
      .getAllByRole('region')
      .map(region => region.getAttribute('aria-label'))
      .filter(label => label !== 'radio');
    expect(order).toEqual(['briefing', 'results', 'usage']);
  });
});
