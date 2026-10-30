/** A pending section holds its card's geometry, never a hole and never a setup hint (D3). */
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseBriefingResult } from '@/hooks/useBriefing';
import type { CardSection, CardsBundle, SectionData } from '@/types/briefing';

vi.mock('@/hooks/useBriefingPreferences', () => ({
  useBriefingPreferences: () => ({ preferences: null }),
}));
vi.mock('../HeroLiaCard', () => ({ HeroLiaCard: () => null }));
vi.mock('../DashboardDateHeading', () => ({ DashboardDateHeading: () => <h1>Today</h1> }));
vi.mock('../QuickAccessCompact', () => ({ QuickAccessCompact: () => null }));
vi.mock('../PortraitHint', () => ({ PortraitHint: () => null }));
vi.mock('../StarterChecklistCard', () => ({ StarterChecklistCard: () => null }));
vi.mock('@/components/pwa/InstallHint', () => ({ InstallHint: () => null }));

import { TodayBriefing } from '../TodayBriefing';

const AT = '2026-10-28T08:00:00Z';

function section<T extends SectionData>(status: CardSection['status'], data: T): CardSection<T> {
  return {
    status,
    data,
    generated_at: AT,
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

/** A section still waiting for its own read, typed as the card it stands for. */
function pendingOf<T extends SectionData>(): CardSection<T> {
  return { ...section('pending', null), data: null };
}

function cardsWith(overrides: Partial<CardsBundle>): CardsBundle {
  // Every other card answered: only a pending one could reach the setup hint.
  const off = section('empty', null);
  return {
    weather: off,
    agenda: off,
    mails: off,
    birthdays: off,
    reminders: off,
    health: off,
    for_you: off,
    tasks: off,
    documents: off,
    workboard: off,
    ...overrides,
  } as CardsBundle;
}

function briefing(cards: CardsBundle): UseBriefingResult {
  return {
    cards,
    windows: {
      birthdays_horizon_days: 7,
      health_window_days: 14,
      agenda_lookahead_hours: 24,
      tasks_horizon_days: 7,
      weather_forecast_days: 5,
    },
    text: undefined,
    loading: true,
    cardsLoading: false,
    textLoading: true,
    textUnavailable: false,
    error: null,
    refetchAll: async () => {},
    refetchSection: async () => {},
    invalidateSection: async () => {},
    refreshingSections: new Set(),
  };
}

const REMINDERS = section('ok', {
  items: [{ id: 'r1', content: 'Call the bakery', trigger_at_local: '09:00' }],
});

describe('the progressive dashboard grid', () => {
  it('renders a local card while the weather read is still pending', async () => {
    renderWithProviders(
      <TodayBriefing
        briefing={briefing(cardsWith({ reminders: REMINDERS, weather: pendingOf() }))}
      />
    );

    expect(screen.getByText('Call the bakery')).toBeInTheDocument();
    expect(screen.getAllByTestId('briefing-card-skeleton')).toHaveLength(1);
    // One announcement for the page, never one per tile (spoken a frame after it mounts).
    expect(await screen.findAllByText('common.loading')).toHaveLength(1);
  });

  it('a pending card never shows the setup hint', async () => {
    renderWithProviders(
      <TodayBriefing
        briefing={briefing(
          cardsWith({
            reminders: REMINDERS,
            weather: pendingOf(),
            agenda: pendingOf(),
            mails: pendingOf(),
          })
        )}
      />
    );

    expect(screen.getAllByTestId('briefing-card-skeleton')).toHaveLength(3);
    expect(screen.queryByText(/not_configured_intro/)).not.toBeInTheDocument();
    expect(await screen.findAllByText('common.loading')).toHaveLength(1);
  });

  it('announces nothing once every section settled', () => {
    renderWithProviders(<TodayBriefing briefing={briefing(cardsWith({ reminders: REMINDERS }))} />);

    expect(screen.queryByTestId('briefing-card-skeleton')).not.toBeInTheDocument();
    expect(screen.queryByText('common.loading')).not.toBeInTheDocument();
  });
});
