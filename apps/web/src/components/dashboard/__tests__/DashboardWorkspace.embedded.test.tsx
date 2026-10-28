import { act, renderWithProviders as render, screen, waitFor } from '@/__tests__/test-utils';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import type { UserStatistics } from '@/hooks/useUserStatistics';
import type { PersonalResults } from '@/hooks/usePersonalResults';
import type { CardsBundle, CardSection, BriefingWindows } from '@/types/briefing';
import type { UserUsageLimitResponse, LimitDetail } from '@/types/usage-limits';
import type { RequestConfig } from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import { DashboardWorkspace } from '../DashboardWorkspace';

const { get, post, auth } = vi.hoisted(() => ({
  get: vi.fn<(path: string, config?: RequestConfig) => Promise<unknown>>(),
  post: vi.fn<(path: string, body: unknown, config?: RequestConfig) => Promise<unknown>>(),
  auth: { id: 'owner-one', is_active: true, full_name: 'Owner one' },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: auth }) }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config: null }) }));
vi.mock('@/hooks/useBriefingPreferences', () => ({
  useBriefingPreferences: () => ({ preferences: null }),
}));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get, post },
  apiClient: { get, post },
}));
vi.mock('@/lib/logger', () => ({ logger: { debug: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/logging-context', () => {
  const withContext = (context: Record<string, unknown>) => context;
  return { useLoggingContext: () => ({ withContext }) };
});
vi.mock('../StarterChecklistCard', () => ({ StarterChecklistCard: () => null }));
vi.mock('../PortraitHint', () => ({ PortraitHint: () => null }));
vi.mock('@/components/pwa/InstallHint', () => ({ InstallHint: () => null }));
vi.mock('@/components/radio/RadioDashboardCard', () => ({
  RadioDashboardCard: () => <p>Native radio</p>,
}));

const hidden: Omit<CardSection, 'data'> & { data: null } = {
  status: 'hidden',
  data: null,
  generated_at: '2026-10-27T08:00:00Z',
  error_code: null,
  error_message: null,
  from_cache: false,
  stale_generated_at: null,
  last_attempt_at: null,
};
const cards: CardsBundle = {
  weather: hidden,
  agenda: hidden,
  mails: hidden,
  birthdays: hidden,
  reminders: hidden,
  health: hidden,
  for_you: hidden,
  tasks: hidden,
  documents: hidden,
  workboard: hidden,
};
const windows: BriefingWindows = {
  birthdays_horizon_days: 7,
  health_window_days: 14,
  agenda_lookahead_hours: 24,
  tasks_horizon_days: 7,
  weather_forecast_days: 5,
};
const statistics: UserStatistics = {
  total_since: '2026-01-01T00:00:00Z',
  current_cycle_start: '2026-10-01T00:00:00Z',
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_cached_tokens: 0,
  total_cost_eur: 0,
  total_messages: 20,
  total_google_api_requests: 0,
  total_google_api_cost_eur: 0,
  cycle_prompt_tokens: 0,
  cycle_completion_tokens: 0,
  cycle_cached_tokens: 0,
  cycle_cost_eur: 0,
  cycle_messages: 2,
  cycle_google_api_requests: 0,
  cycle_google_api_cost_eur: 0,
};
const results: PersonalResults = {
  cycle_start: statistics.current_cycle_start,
  useful_results: 3,
  actions: 2,
  automations: 1,
  commitments_closed: 1,
  measured: true,
};
const limit: LimitDetail = { current: 0, limit: null, usage_pct: null, exceeded: false };
const limits: UserUsageLimitResponse = {
  status: 'ok',
  is_blocked: false,
  blocked_reason: null,
  cycle_tokens: limit,
  cycle_messages: limit,
  cycle_cost: limit,
  absolute_tokens: limit,
  absolute_messages: limit,
  absolute_cost: limit,
  cycle_start: statistics.current_cycle_start,
  cycle_end: '2026-11-01T00:00:00Z',
};
beforeEach(() => {
  auth.id = 'owner-one';
  get.mockReset();
  post.mockReset();
  get.mockImplementation(async path => {
    switch (path) {
      case '/briefing/cards':
        return { cards, windows };
      case '/briefing/synthesis':
        return {
          greeting: { text: 'Native greeting', generated_at: '2026-10-27T08:00:00Z', usage: null },
          synthesis: {
            text: 'Native synthesis',
            generated_at: '2026-10-27T08:00:00Z',
            usage: null,
          },
        };
      case '/product/me/results':
        return results;
      case '/chat/users/me/statistics':
        return statistics;
      case '/usage-limits/me':
        return limits;
      default:
        throw new Error('Unexpected private dashboard reader: ' + path);
    }
  });
});
afterEach(() => vi.useRealTimers());
const reads = (path: string) => get.mock.calls.filter(call => call[0] === path);

it('retains the complete native dashboard across suspension without another text purchase or poll', async () => {
  const view = render(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await screen.findByText('Native synthesis');
  expect(screen.getByText('Native radio')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'dashboard.results.title' })).toBeVisible();
  expect(
    screen.getByRole('heading', { name: 'dashboard.statistics.consumption_title' })
  ).toBeVisible();
  const requests = get.mock.calls.length;
  vi.useFakeTimers();
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active={false} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(65_000);
  });
  expect(get).toHaveBeenCalledTimes(requests);
  expect(screen.queryByText('Native synthesis')).not.toBeVisible();
  vi.useRealTimers();
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await waitFor(() => expect(reads('/briefing/cards')).toHaveLength(2));
  expect(reads('/briefing/synthesis')).toHaveLength(1);
  expect(screen.getByText('Native synthesis')).toBeVisible();
});

it('fences an obsolete owner and aborts the statistics and limit transports when hidden', async () => {
  const view = render(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await screen.findByText('Native synthesis');
  const statsSignal = reads('/chat/users/me/statistics')[0][1]?.signal;
  const limitsSignal = reads('/usage-limits/me')[0][1]?.signal;
  expect(statsSignal).toBeDefined();
  expect(limitsSignal).toBeDefined();
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active={false} />);
  expect(statsSignal?.aborted).toBe(true);
  expect(limitsSignal?.aborted).toBe(true);
  auth.id = 'owner-two';
  view.rerender(<DashboardWorkspace lng="en" ownerId="owner-one" active />);
  await act(async () => {});
  expect(screen.queryByText('Native synthesis')).not.toBeInTheDocument();
  expect(reads('/briefing/synthesis')).toHaveLength(1);
});

it('retains private invalidations while hidden and refreshes only cards when resumed', async () => {
  const reminderCards: CardsBundle = {
    ...cards,
    reminders: {
      ...hidden,
      status: 'ok',
      data: {
        items: [
          { id: 'cached', content: 'Cached reminder', trigger_at_local: '2026-10-27T18:00:00' },
        ],
      },
    },
  };
  const original = get.getMockImplementation();
  get.mockImplementation((path, config) =>
    path === '/briefing/cards'
      ? Promise.resolve({ cards: reminderCards, windows })
      : original!(path, config)
  );
  post.mockResolvedValue({
    cards: {
      ...reminderCards,
      reminders: {
        ...reminderCards.reminders,
        data: {
          items: [
            { id: 'fresh', content: 'Fresh after hidden', trigger_at_local: '2026-10-27T18:00:00' },
          ],
        },
      },
    },
    windows,
  });
  const view = render(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await screen.findByText('Cached reminder');
  await screen.findByText('Native synthesis');
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active={false} />);
  act(() => publishApplicationResources(auth.id, new Set(['reminders'])));
  expect(post).not.toHaveBeenCalled();
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await screen.findByText('Fresh after hidden');
  expect(post.mock.calls.map(call => [call[0], call[1]])).toEqual([
    ['/briefing/refresh-cards', { sections: ['reminders'] }],
  ]);
  expect(reads('/briefing/synthesis')).toHaveLength(1);
});

it('withdraws SMS-derived text received while hidden without buying a replacement', async () => {
  const view = render(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await screen.findByText('Native synthesis');
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active={false} />);
  act(() => publishApplicationResources(auth.id, new Set(['sms'])));
  view.rerender(<DashboardWorkspace lng="en" ownerId={auth.id} active />);
  await waitFor(() => expect(screen.queryByText('Native synthesis')).not.toBeInTheDocument());
  expect(screen.getByText('dashboard.briefing.text_unavailable')).toBeVisible();
  expect(reads('/briefing/synthesis')).toHaveLength(1);
});
