/**
 * The home page reads `/config` once per visit — the dashboard body's own read.
 *
 * The page used to call `useAppConfig()` and drop the answer, while the body
 * made its own call: one extra GET on every visit that nothing could see, since
 * every `useApiQuery` owns its data. The radio's progressive layout comes from
 * the dashboard LAYOUT's read instead, handed down as a seed: the body renders
 * the radio from it on the first frame, before its own read answers.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { ReactNode } from 'react';

import { act, renderWithProviders, screen } from '@/__tests__/test-utils';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import type { UseBriefingResult } from '@/hooks/useBriefing';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner-1', is_active: true }, isLoading: false }),
}));
vi.mock('@/hooks/useLanguageParam', () => ({ useLanguageParam: () => 'fr' }));
vi.mock('@/hooks/usePersonalResults', () => ({
  usePersonalResults: () => ({ results: null, firstLoad: false, error: null }),
}));
const { briefing } = vi.hoisted(() => {
  const value: UseBriefingResult = {
    cards: undefined,
    windows: undefined,
    text: undefined,
    loading: false,
    cardsLoading: false,
    textLoading: false,
    textUnavailable: false,
    error: null,
    refetchAll: async () => {},
    refetchSection: async () => {},
    invalidateSection: async () => {},
    refreshingSections: new Set(),
  };
  return { briefing: value };
});
vi.mock('@/hooks/useBriefing', () => ({ useBriefing: () => briefing }));
vi.mock('@/components/dashboard/TodayBriefing', () => ({
  TodayBriefing: ({ aboveBriefing }: { aboveBriefing?: ReactNode }) => <>{aboveBriefing}</>,
}));
vi.mock('@/components/radio/RadioDashboardCard', () => ({
  RadioDashboardCard: ({ enabled }: { enabled: boolean }) => (
    <section aria-label="radio" data-enabled={String(enabled)} />
  ),
}));
vi.mock('@/components/dashboard/ResultsSummary', () => ({ ResultsSummary: () => null }));
vi.mock('@/components/dashboard/UsageStatistics', () => ({ UsageStatistics: () => null }));

import DashboardPage from '../page';

const SEED: AppConfig = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'test-embedding',
    journals_enabled: true,
    radio_enabled: true,
  },
  api_version: 'test',
};

let configReads: number;

beforeEach(() => {
  configReads = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(input => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, 'https://lia.example.test').pathname;
      if (path !== '/api/v1/config') throw new Error(`Unexpected API read: ${path}`);
      configReads += 1;
      return new Promise<Response>(() => {});
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the home page configuration read', () => {
  it('sends one /config request: the dashboard body’s', async () => {
    renderWithProviders(<DashboardPage params={Promise.resolve({ lng: 'fr' })} />);
    await act(async () => {});

    expect(configReads).toBe(1);
  });

  it('renders the radio from the layout’s seed on the first frame, and still reads once', async () => {
    renderWithProviders(
      <AppConfigSeedContext.Provider value={SEED}>
        <DashboardPage params={Promise.resolve({ lng: 'fr' })} />
      </AppConfigSeedContext.Provider>
    );

    expect(screen.getByRole('region', { name: 'radio' })).toHaveAttribute('data-enabled', 'true');
    await act(async () => {});
    expect(configReads).toBe(1);
  });
});
