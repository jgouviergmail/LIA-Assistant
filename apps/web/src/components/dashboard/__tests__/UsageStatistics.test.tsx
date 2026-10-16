import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, within } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { UseUsageLimitsReturn } from '@/hooks/useUsageLimits';
import type { UserStatistics, UseUserStatisticsReturn } from '@/hooks/useUserStatistics';
import type { LimitDetail, UserUsageLimitResponse } from '@/types/usage-limits';

import { UsageStatistics } from '../UsageStatistics';

const { statisticsHook, limitsHook, refetch } = vi.hoisted(() => ({
  statisticsHook: vi.fn<() => UseUserStatisticsReturn>(),
  limitsHook: vi.fn<() => UseUsageLimitsReturn>(),
  refetch: vi.fn<() => Promise<void>>(),
}));

vi.mock('@/hooks/useUserStatistics', () => ({ useUserStatistics: statisticsHook }));
vi.mock('@/hooks/useUsageLimits', () => ({ useUsageLimits: limitsHook }));

function statistics(over: Partial<UserStatistics> = {}): UserStatistics {
  return {
    current_cycle_start: '2026-08-01T00:00:00Z',
    total_since: '2026-01-01T00:00:00Z',
    cycle_messages: 42,
    total_messages: 420,
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
    ...over,
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

function limits(over: Partial<UserUsageLimitResponse> = {}): UserUsageLimitResponse {
  return {
    status: 'ok',
    is_blocked: false,
    blocked_reason: null,
    cycle_tokens: limit(),
    cycle_messages: limit(),
    cycle_cost: limit(),
    absolute_tokens: limit(),
    absolute_messages: limit(),
    absolute_cost: limit(),
    cycle_start: '2026-08-01T00:00:00Z',
    cycle_end: '2026-09-01T00:00:00Z',
    ...over,
  };
}

function readStatistics(over: Partial<UseUserStatisticsReturn> = {}) {
  statisticsHook.mockReturnValue({
    statistics: statistics(),
    isLoading: false,
    error: null,
    refetch,
    ...over,
  });
}

function readLimits(value: UserUsageLimitResponse | null) {
  limitsHook.mockReturnValue({
    limits: value,
    isLoading: false,
    isBlocked: false,
    blockReason: null,
    refetch,
  });
}

function row(label: string) {
  return screen.getByRole('rowheader', { name: label }).closest('tr')!;
}

beforeEach(() => {
  vi.clearAllMocks();
  refetch.mockResolvedValue(undefined);
  readStatistics();
  readLimits(null);
});

describe('UsageStatistics — consumption period and totals', () => {
  it('opens by default and remains a native disclosure the reader can fold', () => {
    renderWithProviders(<UsageStatistics />);
    const details = screen.getByRole('group');
    expect(details).toHaveAttribute('open');
    expect(screen.getByText('42')).toBeVisible();
    details.removeAttribute('open');
    expect(screen.getByText('42')).not.toBeVisible();
  });

  it('associates every metric with its period and lifetime values in a single table', () => {
    renderWithProviders(<UsageStatistics />);
    expect(
      screen.getByRole('table', { name: 'dashboard.statistics.consumption_title' })
    ).toBeVisible();
    expect(screen.getByRole('columnheader', { name: 'dashboard.statistics.period' })).toBeVisible();
    expect(screen.getByRole('columnheader', { name: 'dashboard.statistics.total' })).toBeVisible();
    const expected = [
      ['messages.title', '42', '420'],
      ['tokens.title', '1 700', '17 000'],
      ['prompt_tokens', '1 000', '10 000'],
      ['completion_tokens', '500', '5 000'],
      ['cached_tokens', '200', '2 000'],
      ['google_api.title', '7', '70'],
      ['google_api_cost', '0,12 €', '1,20 €'],
      ['cost.title', '1,23 €', '12,30 €'],
    ];
    for (const [label, period, total] of expected) {
      const cells = within(row(`dashboard.statistics.${label}`)).getAllByRole('cell');
      expect(cells.map(cell => cell.textContent)).toEqual([period, total]);
    }
    expect(screen.getByText('dashboard.statistics.cycle_dates')).toBeVisible();
    expect(screen.getByText('dashboard.statistics.since')).toBeVisible();
    expect(statisticsHook).toHaveBeenCalledTimes(1);
    expect(limitsHook).toHaveBeenCalledTimes(1);
  });

  it('does not manufacture zero consumption when the payload is absent', () => {
    readStatistics({ statistics: null });
    renderWithProviders(<UsageStatistics />);
    expect(screen.getByText('dashboard.statistics.unavailable')).toBeVisible();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.queryByText('0,00 €')).not.toBeInTheDocument();
  });

  it('keeps a measured zero cost and zero cache as real values', () => {
    readStatistics({ statistics: statistics({ cycle_cost_eur: 0, cycle_cached_tokens: 0 }) });
    renderWithProviders(<UsageStatistics />);
    expect(
      within(row('dashboard.statistics.cost.title')).getAllByRole('cell')[0]
    ).toHaveTextContent('0,00 €');
    expect(
      within(row('dashboard.statistics.cached_tokens')).getAllByRole('cell')[0]
    ).toHaveTextContent(/^0$/);
  });

  it('keeps the received values and dates while a populated block refreshes', () => {
    const { rerender } = renderWithProviders(<UsageStatistics />);
    const table = screen.getByRole('table');
    readStatistics({ isLoading: true });
    rerender(<UsageStatistics />);
    expect(screen.getByRole('table')).toBe(table);
    expect(screen.getByText('42')).toBeVisible();
    expect(screen.getByText('dashboard.statistics.cycle_dates')).toBeVisible();
    expect(screen.getByText('dashboard.statistics.since')).toBeVisible();
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows loading rather than empty or fabricated values before the first payload', () => {
    readStatistics({ statistics: null, isLoading: true });
    renderWithProviders(<UsageStatistics />);
    expect(screen.getByRole('status', { name: 'common.loading' })).toBeVisible();
    expect(screen.queryByText('dashboard.statistics.unavailable')).not.toBeInTheDocument();
    expect(screen.queryByText('0,00 €')).not.toBeInTheDocument();
  });

  it('explains a failed refresh while retaining the last received values and supports retry', async () => {
    readStatistics({ error: 'internal detail must not appear' });
    const { user } = renderWithProviders(<UsageStatistics />);
    expect(screen.getByRole('status')).toHaveTextContent('dashboard.statistics.refresh_error');
    expect(screen.getByText('42')).toBeVisible();
    expect(screen.queryByText('internal detail must not appear')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('keeps retry focused and prevents overlapping manual refreshes', async () => {
    let finish!: () => void;
    refetch.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        })
    );
    readStatistics({ error: 'offline' });
    const { user } = renderWithProviders(<UsageStatistics />);
    const retry = screen.getByRole('button', { name: 'common.retry' });
    await user.click(retry);
    expect(retry).toHaveFocus();
    expect(retry).toHaveAttribute('aria-disabled', 'true');
    await user.click(retry);
    expect(refetch).toHaveBeenCalledTimes(1);
    await act(async () => {
      finish();
    });
    expect(retry).toHaveFocus();
    expect(retry).toHaveAttribute('aria-disabled', 'false');
  });

  it('restores focus to the consumption summary when success removes the retry control', async () => {
    let finish!: () => void;
    refetch.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        })
    );
    readStatistics({ error: 'offline' });
    const { user, rerender } = renderWithProviders(<UsageStatistics />);
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    readStatistics({ error: null });
    rerender(<UsageStatistics />);
    await act(async () => {
      finish();
    });
    expect(screen.queryByRole('button', { name: 'common.retry' })).not.toBeInTheDocument();
    expect(
      screen
        .getByText('dashboard.statistics.consumption_title', { selector: 'h2' })
        .closest('summary')
    ).toHaveFocus();
  });

  it('does not steal focus when recovery finishes after the reader moved elsewhere', async () => {
    let finish!: () => void;
    refetch.mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        })
    );
    readStatistics({ error: 'offline' });
    const { user, rerender } = renderWithProviders(
      <>
        <button>Other action</button>
        <UsageStatistics />
      </>
    );
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    await user.click(screen.getByRole('button', { name: 'Other action' }));
    readStatistics({ error: null });
    rerender(
      <>
        <button>Other action</button>
        <UsageStatistics />
      </>
    );
    await act(async () => {
      finish();
    });
    expect(screen.getByRole('button', { name: 'Other action' })).toHaveFocus();
  });

  it('omits unreadable dates while keeping the received counters available', () => {
    readStatistics({
      statistics: statistics({ current_cycle_start: 'bad-date', total_since: 'bad-date' }),
    });
    renderWithProviders(<UsageStatistics />);
    expect(screen.getByText('42')).toBeVisible();
    expect(screen.queryByText('dashboard.statistics.cycle_dates')).not.toBeInTheDocument();
    expect(screen.queryByText('dashboard.statistics.since')).not.toBeInTheDocument();
  });

  it('keeps limits available even when statistics fail', () => {
    readStatistics({ statistics: null, error: 'offline' });
    readLimits(limits({ cycle_messages: limit(42, 200), absolute_cost: limit(12.3, 100) }));
    renderWithProviders(<UsageStatistics />);
    expect(screen.getByText('usage_limits.tile.title_period')).toBeVisible();
    expect(screen.getByText('usage_limits.tile.title_absolute')).toBeVisible();
    expect(screen.getAllByRole('progressbar')).toHaveLength(2);
  });

  it('does not invent a configured limit when the feature is absent or all dimensions are unlimited', () => {
    const { rerender } = renderWithProviders(<UsageStatistics />);
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    readLimits(limits());
    rerender(<UsageStatistics />);
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.queryByText('usage_limits.tile.title_period')).not.toBeInTheDocument();
    expect(screen.getByText('42')).toBeVisible();
  });
});
