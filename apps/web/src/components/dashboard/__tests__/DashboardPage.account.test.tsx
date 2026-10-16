import { type ContextType, type ReactNode, useEffect } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  act,
  cleanup,
  fireEvent,
  renderWithProviders,
  screen,
  within,
} from '@/__tests__/test-utils';
import DashboardPage from '@/app/[lng]/dashboard/page';
import type { UserStatistics } from '@/hooks/useUserStatistics';
import { AuthContext, type User } from '@/lib/auth';
import { LoggingProvider } from '@/lib/logging-context';
import type { LimitDetail, UserUsageLimitResponse } from '@/types/usage-limits';

const { radioMounts } = vi.hoisted(() => ({ radioMounts: vi.fn() }));

// Keep unrelated dashboard readers out of this account-lifetime test. The
// statistics component, both of its hooks, auth context and API client are real.
vi.mock('@/hooks/usePersonalResults', () => ({
  usePersonalResults: () => ({ results: undefined, firstLoad: false, error: null }),
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({ config: null, loading: false, error: null }),
}));
vi.mock('@/components/dashboard/ResultsSummary', () => ({ ResultsSummary: () => null }));
vi.mock('@/components/dashboard/TodayBriefing', () => ({
  TodayBriefing: ({ aboveBriefing }: { aboveBriefing?: ReactNode }) => <>{aboveBriefing}</>,
}));
vi.mock('@/components/radio/RadioDashboardCard', () => ({
  RadioDashboardCard: function RadioLifetimeProbe() {
    useEffect(() => {
      radioMounts();
    }, []);
    return <input aria-label="Radio station" defaultValue="" />;
  },
}));

const STATISTICS = '/api/v1/chat/users/me/statistics';
const LIMITS = '/api/v1/usage-limits/me';
const params = Promise.resolve({ lng: 'fr' });

interface PendingRead {
  path: string;
  respond: (body: UserStatistics | UserUsageLimitResponse) => void;
}

let pending: PendingRead[];

function account(id: string): User {
  return {
    id,
    email: `${id}@example.test`,
    is_active: true,
    is_verified: true,
    is_superuser: false,
    memory_enabled: true,
    execution_mode: 'pipeline',
    voice_enabled: false,
    voice_mode_enabled: false,
    voice_stt_mode: 'local',
    tokens_display_enabled: false,
    debug_panel_enabled: false,
    response_display_mode: 'streaming',
    onboarding_completed: true,
  };
}

function session(user: User): NonNullable<ContextType<typeof AuthContext>> {
  return {
    user,
    isLoading: false,
    login: async () => ({ user, mfaRequired: false, mfaToken: null }),
    verifyMfa: async () => user,
    register: async () => user,
    logout: async () => {},
    initiateGoogleOAuth: async () => {},
    completeNativeSignIn: async () => ({ mfaRequired: false }),
    refreshUser: async () => true,
  };
}

function page(user: User) {
  return (
    <AuthContext.Provider value={session(user)}>
      <LoggingProvider traceId="account-lifetime-test">
        <DashboardPage params={params} />
      </LoggingProvider>
    </AuthContext.Provider>
  );
}

function statistics(cycleMessages: number, totalMessages: number): UserStatistics {
  return {
    current_cycle_start: '2026-10-01T00:00:00Z',
    total_since: '2026-01-01T00:00:00Z',
    cycle_messages: cycleMessages,
    total_messages: totalMessages,
    cycle_prompt_tokens: 1000,
    cycle_completion_tokens: 500,
    cycle_cached_tokens: 200,
    total_prompt_tokens: 10_000,
    total_completion_tokens: 5_000,
    total_cached_tokens: 2_000,
    cycle_google_api_requests: 7,
    total_google_api_requests: 70,
    cycle_google_api_cost_eur: 0.12,
    total_google_api_cost_eur: 1.2,
    cycle_cost_eur: 1.23,
    total_cost_eur: 12.3,
  };
}

function limit(current = 0, maximum: number | null = null): LimitDetail {
  return {
    current,
    limit: maximum,
    usage_pct: maximum ? (current / maximum) * 100 : null,
    exceeded: false,
  };
}

function limits(current: number): UserUsageLimitResponse {
  return {
    status: 'ok',
    is_blocked: false,
    blocked_reason: null,
    cycle_tokens: limit(),
    cycle_messages: limit(current, 100),
    cycle_cost: limit(),
    absolute_tokens: limit(),
    absolute_messages: limit(),
    absolute_cost: limit(),
    cycle_start: '2026-10-01T00:00:00Z',
    cycle_end: '2026-11-01T00:00:00Z',
  };
}

function reads(path: string): PendingRead[] {
  return pending.filter(read => read.path === path);
}

async function respond(read: PendingRead, body: UserStatistics | UserUsageLimitResponse) {
  await act(async () => {
    read.respond(body);
  });
}

function expectMessages(cycle: string, total: string) {
  const row = screen
    .getByRole('rowheader', { name: 'dashboard.statistics.messages.title' })
    .closest('tr');
  if (!row) throw new Error('Messages must belong to their table row');
  expect(
    within(row)
      .getAllByRole('cell')
      .map(cell => cell.textContent)
  ).toEqual([cycle, total]);
}

beforeEach(() => {
  vi.useFakeTimers();
  radioMounts.mockClear();
  pending = [];
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, 'https://lia.example.test').pathname;
      if (path !== STATISTICS && path !== LIMITS) throw new Error(`Unexpected API read: ${path}`);
      expect(init?.credentials).toBe('include');
      return new Promise<Response>(resolve => {
        pending.push({ path, respond: body => resolve(Response.json(body)) });
      });
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('DashboardPage consumption ownership', () => {
  it('removes the previous account counters and limits before the new account replies', async () => {
    const { rerender } = renderWithProviders(page(account('A')), { advanceTimers: true });
    await respond(reads(STATISTICS)[0], statistics(101, 1001));
    await respond(reads(LIMITS)[0], limits(13));
    expectMessages('101', '1 001');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '13');

    rerender(page(account('B')));

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'common.loading' })).toBeVisible();
    expect(reads(STATISTICS)).toHaveLength(2);
    expect(reads(LIMITS)).toHaveLength(2);
    await respond(reads(STATISTICS)[1], statistics(202, 2002));
    await respond(reads(LIMITS)[1], limits(26));
    expectMessages('202', '2 002');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '26');
  });

  it('ignores both former account replies when they arrive after the new account data', async () => {
    const { rerender } = renderWithProviders(page(account('A')), { advanceTimers: true });
    const oldStatistics = reads(STATISTICS)[0];
    const oldLimits = reads(LIMITS)[0];

    rerender(page(account('B')));

    expect(reads(STATISTICS)).toHaveLength(2);
    expect(reads(LIMITS)).toHaveLength(2);
    await respond(reads(STATISTICS)[1], statistics(202, 2002));
    await respond(reads(LIMITS)[1], limits(26));
    await respond(oldStatistics, statistics(101, 1001));
    await respond(oldLimits, limits(13));

    expectMessages('202', '2 002');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '26');
  });

  it('keeps consumption and radio mounted across same-account rerenders and polling', async () => {
    const owner = account('A');
    const { rerender } = renderWithProviders(page(owner), { advanceTimers: true });
    await respond(reads(STATISTICS)[0], statistics(101, 1001));
    await respond(reads(LIMITS)[0], limits(13));
    const table = screen.getByRole('table');
    const radio = screen.getByRole('textbox', { name: 'Radio station' });
    const disclosure = screen.getByRole('group');
    fireEvent.change(radio, { target: { value: 'Jazz' } });
    disclosure.removeAttribute('open');

    rerender(page(owner));
    await act(async () => {});

    expect(reads(STATISTICS)).toHaveLength(1);
    expect(reads(LIMITS)).toHaveLength(1);
    expect(radioMounts).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('textbox', { name: 'Radio station' })).toBe(radio);
    expect(radio).toHaveValue('Jazz');
    expect(disclosure).not.toHaveAttribute('open');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(reads(STATISTICS)).toHaveLength(3);
    expect(reads(LIMITS)).toHaveLength(2);
    await respond(reads(STATISTICS)[2], statistics(102, 1002));
    await respond(reads(LIMITS)[1], limits(14));
    expect(screen.getByRole('table', { hidden: true })).toBe(table);
    expect(screen.getByRole('textbox', { name: 'Radio station' })).toBe(radio);
    expect(radio).toHaveValue('Jazz');
    expect(radioMounts).toHaveBeenCalledTimes(1);
    expect(reads(STATISTICS)).toHaveLength(3);
    expect(reads(LIMITS)).toHaveLength(2);
    expect(disclosure).not.toHaveAttribute('open');
    disclosure.setAttribute('open', '');
    expectMessages('102', '1 002');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '14');
  });
});
