/**
 * HabitExplanation (ADR-214) — honest provenance for a habit row.
 *
 * What must hold: the block loads ONLY when opened; a recurring habit shows
 * the ledger's real occurrence dates with an overflow stated (never silently
 * truncated); the enforced thresholds are published; a load failure is an
 * alert, not silence. The i18n mock echoes keys.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import type { HabitExplanationPayload } from '../HabitExplanation';

const queryState = {
  data: undefined as HabitExplanationPayload | undefined,
  loading: false,
  error: null as Error | null,
};
const useApiQuery = vi.fn((_path: string, opts: { enabled?: boolean }) =>
  opts.enabled ? queryState : { data: undefined, loading: false, error: null }
);
vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (path: string, opts: { enabled?: boolean }) => useApiQuery(path, opts),
}));

import { HabitExplanation } from '../HabitExplanation';

function payload(over: Partial<HabitExplanationPayload> = {}): HabitExplanationPayload {
  return {
    kind: 'recurring_request',
    key: 'email+contact',
    payload: { shape: 'weekly' },
    positive_signals: 3,
    negative_signals: 0,
    status: 'active',
    last_observed_at: '2026-08-03T09:00:00Z',
    thresholds: { min_distinct_days: 4, weekly_min_same_dow: 4 },
    observed_days: ['2026-08-03', '2026-07-27', '2026-07-20'],
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  queryState.data = undefined;
  queryState.loading = false;
  queryState.error = null;
});

async function openDisclosure() {
  const { user } = renderWithProviders(<HabitExplanation lng="fr" habitId="h-1" />);
  await user.click(screen.getByText('settings.habits.explanation.title'));
}

describe('HabitExplanation', () => {
  it('fetches nothing while closed', () => {
    renderWithProviders(<HabitExplanation lng="fr" habitId="h-1" />);
    expect(useApiQuery).toHaveBeenCalledWith(
      '/habits/h-1/explanation',
      expect.objectContaining({ enabled: false })
    );
  });

  it('shows the real observed dates and the published thresholds', async () => {
    queryState.data = payload();
    await openDisclosure();
    expect(screen.getByText('settings.habits.explanation.observed_label')).toBeInTheDocument();
    // Dates render short-formatted and joined; the thresholds are checkable.
    expect(screen.getByText(/min_distinct_days=4/)).toBeInTheDocument();
    expect(screen.getByText(/weekly_min_same_dow=4/)).toBeInTheDocument();
  });

  it('states the overflow beyond the shown dates', async () => {
    queryState.data = payload({
      observed_days: Array.from(
        { length: 12 },
        (_, k) => `2026-07-${String(k + 1).padStart(2, '0')}`
      ),
    });
    await openDisclosure();
    expect(screen.getByText(/settings\.habits\.explanation\.more_days/)).toBeInTheDocument();
  });

  it('a window habit (no dates) still publishes its thresholds', async () => {
    queryState.data = payload({
      kind: 'active_window',
      observed_days: [],
      thresholds: { presence_min: 0.55 },
    });
    await openDisclosure();
    expect(
      screen.queryByText('settings.habits.explanation.observed_label')
    ).not.toBeInTheDocument();
    expect(screen.getByText(/presence_min=0.55/)).toBeInTheDocument();
  });

  it('a load failure is an alert, not silence', async () => {
    queryState.error = new Error('boom');
    await openDisclosure();
    expect(screen.getByRole('alert')).toHaveTextContent('settings.habits.explanation.error');
  });
});
