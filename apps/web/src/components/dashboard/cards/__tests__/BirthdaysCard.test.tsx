/**
 * The birthdays card says the window the API actually looked at.
 *
 * Prompt audit 2026-09-12 (A.6): the six locales said « Rien dans les 14
 * prochains jours » while the fetcher looked 7 days ahead on any instance
 * living on the constants. The number now travels with the cards payload
 * (`windows.birthdays_horizon_days`) and reaches the empty state as `count`.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { renderWithProviders, screen } from '@/__tests__/test-utils';

// A `t` that shows its options, so the interpolation contract is visible.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && Object.keys(options).length > 0 ? `${key}|${JSON.stringify(options)}` : key,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: vi.fn() }));

import { BirthdaysCard } from '../BirthdaysCard';
import type { BirthdaysData, BriefingWindows, CardSection } from '@/types/briefing';

const WINDOWS: BriefingWindows = {
  birthdays_horizon_days: 7,
  health_window_days: 14,
  agenda_lookahead_hours: 24,
  tasks_horizon_days: 7,
  weather_forecast_days: 5,
};

function emptySection(): CardSection<BirthdaysData> {
  return {
    status: 'empty',
    data: null,
    generated_at: '2026-09-12T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

const props = { isRefreshing: false, onRefresh: vi.fn(), staggerIndex: 0 };

describe('BirthdaysCard empty state', () => {
  it('names the horizon the API published, as the plural count', () => {
    renderWithProviders(<BirthdaysCard section={emptySection()} windows={WINDOWS} {...props} />);
    expect(
      screen.getByText('dashboard.briefing.cards.birthdays.empty|{"count":7}')
    ).toBeInTheDocument();
  });

  it('follows the API when the instance looks further ahead', () => {
    renderWithProviders(
      <BirthdaysCard
        section={emptySection()}
        windows={{ ...WINDOWS, birthdays_horizon_days: 30 }}
        {...props}
      />
    );
    expect(
      screen.getByText('dashboard.briefing.cards.birthdays.empty|{"count":30}')
    ).toBeInTheDocument();
  });
});
