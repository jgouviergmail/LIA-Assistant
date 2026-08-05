/**
 * HabitsSettings (ADR-214) — flag/availability gating, honest verdicts,
 * the master toggle, row actions through `RowActions` (pause / block /
 * delete, resume on inactive rows) and the confirmed bulk forget.
 *
 * The i18n mock echoes keys (no interpolation): assertions pin KEYS, and the
 * window badges pin the real formatted hours (locale-independent digits).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { Habit, HabitsOverview, HabitsProfileClass } from '@/hooks/useHabits';
import { formatWindow } from '@/hooks/useHabits';

const setStatus = vi.fn(async () => true);
const remove = vi.fn(async () => true);
const removeAll = vi.fn(async () => true);
const setEnabled = vi.fn(async () => true);
const recompute = vi.fn(async () => true);
const refetch = vi.fn();

const state = {
  flagOn: true,
  unavailable: false,
  loadError: false,
  overview: null as HabitsOverview | null,
};

vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: () => ({
    config: { features: { habits_enabled: state.flagOn } },
  }),
}));
// A PARTIAL hook mock is its own defect: the component would call an
// undefined action and the suite would blame the component.
vi.mock('@/hooks/useHabits', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useHabits')>();
  return {
    ...original,
    useHabits: () => ({
      overview: state.overview,
      loading: false,
      unavailable: state.unavailable,
      loadError: state.loadError,
      refetch,
      setStatus,
      remove,
      removeAll,
      setEnabled,
      recompute,
    }),
  };
});

import { HabitsSettings } from '../HabitsSettings';

function habit(over: Partial<Habit> = {}): Habit {
  return {
    id: 'h-1',
    kind: 'active_window',
    key: 'weekday:morning',
    payload: {
      version: 1,
      day_class: 'weekday',
      windows: [{ start_hour: 8, end_hour: 10, presence: 0.9 }],
    },
    status: 'active',
    positive_signals: 2,
    negative_signals: 0,
    last_observed_at: '2026-08-04T04:00:00Z',
    created_at: '2026-07-20T04:00:00Z',
    ...over,
  };
}

function profileClass(over: Partial<HabitsProfileClass> = {}): HabitsProfileClass {
  return {
    verdict: 'none',
    windows: [],
    n_eff: 0,
    required_n_eff: 12,
    bin_presence: Array<number>(24).fill(0),
    ...over,
  };
}

function overview(over: Partial<HabitsOverview> = {}): HabitsOverview {
  return {
    habits_enabled: true,
    profile: {
      computed_at: '2026-08-05T04:10:00Z',
      weekday: profileClass({
        verdict: 'windows',
        windows: [
          { start_hour: 8, end_hour: 10, presence: 0.92 },
          { start_hour: 21, end_hour: 23, presence: 0.88 },
        ],
        n_eff: 22.5,
      }),
      weekend: profileClass({ n_eff: 8.1, required_n_eff: 6 }),
      active_days_fraction: 0.85,
      sparse: false,
    },
    habits: [habit()],
    candidates: [],
    candidates_more: 0,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.flagOn = true;
  state.unavailable = false;
  state.loadError = false;
  state.overview = overview();
});

function renderSection() {
  return render(<HabitsSettings lng="fr" collapsible={false} />);
}

describe('HabitsSettings', () => {
  it('renders nothing when the instance flag is off (gate-keeper)', () => {
    state.flagOn = false;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the surface is unavailable (404-tolerance)', () => {
    state.unavailable = true;
    const { container } = renderSection();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the claimed windows as formatted hour badges', () => {
    renderSection();
    expect(screen.getByText('08:00–10:00')).toBeInTheDocument();
    expect(screen.getByText('21:00–23:00')).toBeInTheDocument();
    // The weekend class states its honest verdict instead of fake windows.
    expect(screen.getByText('settings.habits.verdict.none')).toBeInTheDocument();
  });

  it('states the sparse verdict for occasional users', () => {
    state.overview = overview({
      profile: {
        computed_at: '2026-08-05T04:10:00Z',
        weekday: profileClass({ verdict: 'sparse' }),
        weekend: profileClass({ verdict: 'sparse', required_n_eff: 6 }),
        active_days_fraction: 0.2,
        sparse: true,
      },
      habits: [],
    });
    renderSection();
    expect(screen.getAllByText('settings.habits.verdict.sparse')).toHaveLength(2);
  });

  it('the master toggle has an accessible name and drives the preference', async () => {
    renderSection();
    const toggle = screen.getByRole('switch', { name: 'settings.habits.enabled_label' });
    fireEvent.click(toggle);
    await waitFor(() => expect(setEnabled).toHaveBeenCalledWith(false));
  });

  it('learning disabled hides the profile but keeps the toggle reachable', () => {
    state.overview = overview({ habits_enabled: false });
    renderSection();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.queryByText('08:00–10:00')).not.toBeInTheDocument();
  });

  it('pauses an active habit through its row actions', async () => {
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'settings.habits.pause_label' }));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith('h-1', 'paused'));
  });

  it('a paused habit offers resume instead of pause', async () => {
    state.overview = overview({ habits: [habit({ status: 'paused' })] });
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'settings.habits.resume_label' }));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith('h-1', 'active'));
    expect(
      screen.queryByRole('button', { name: 'settings.habits.pause_label' })
    ).not.toBeInTheDocument();
  });

  it('blocks a habit (never-relearn tombstone)', async () => {
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'settings.habits.block_label' }));
    await waitFor(() => expect(setStatus).toHaveBeenCalledWith('h-1', 'blocked'));
  });

  it('deletes one habit', async () => {
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: 'settings.habits.delete_label' }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith('h-1'));
  });

  it('forget-everything requires an explicit confirmation', async () => {
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: /forget_all_label/ }));
    // The dialog is the consent gate: nothing is deleted before confirming.
    expect(removeAll).not.toHaveBeenCalled();
    const confirmButton = await screen.findByRole('button', {
      name: 'settings.habits.forget_all_confirm',
    });
    fireEvent.click(confirmButton);
    await waitFor(() => expect(removeAll).toHaveBeenCalled());
  });

  it('the insufficient verdict shows a quantified unlock progressbar', () => {
    state.overview = overview({
      profile: {
        computed_at: '2026-08-05T04:10:00Z',
        weekday: profileClass({ verdict: 'insufficient', n_eff: 5.2 }),
        weekend: profileClass({ verdict: 'insufficient', n_eff: 2.0, required_n_eff: 6 }),
        active_days_fraction: 0.6,
        sparse: false,
      },
      habits: [],
    });
    renderSection();
    const bars = screen.getAllByRole('progressbar');
    expect(bars).toHaveLength(2);
    // The published threshold quantifies the unlock — never a re-declared
    // frontend constant, never an unquantified 'still learning'.
    expect(bars[0]).toHaveAttribute('aria-valuenow', '5');
    expect(bars[0]).toHaveAttribute('aria-valuemax', '12');
    expect(bars[1]).toHaveAttribute('aria-valuenow', '2');
    expect(bars[1]).toHaveAttribute('aria-valuemax', '6');
  });

  it('recompute-now runs the retroactive aggregation on demand', async () => {
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: /recompute_label/ }));
    await waitFor(() => expect(recompute).toHaveBeenCalled());
  });

  it('recompute sits left of forget-all on the same actions row', () => {
    renderSection();
    const recomputeBtn = screen.getByRole('button', { name: /recompute_label/ });
    const forgetBtn = screen.getByRole('button', { name: /forget_all_label/ });
    // Same row container, recompute first (owner arbitration 2026-08-05).
    expect(recomputeBtn.parentElement).toBe(forgetBtn.parentElement);
    expect(
      recomputeBtn.compareDocumentPosition(forgetBtn) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('recompute stays reachable before the first compute (retroactive entry point)', () => {
    state.overview = overview({
      profile: {
        computed_at: null,
        weekday: profileClass({ verdict: 'insufficient' }),
        weekend: profileClass({ verdict: 'insufficient', required_n_eff: 6 }),
        active_days_fraction: 0,
        sparse: false,
      },
      habits: [],
    });
    renderSection();
    expect(screen.getByRole('button', { name: /recompute_label/ })).toBeInTheDocument();
    // Nothing learned yet → nothing to forget: the destructive button is absent.
    expect(screen.queryByRole('button', { name: /forget_all_label/ })).not.toBeInTheDocument();
  });

  it('candidates under observation show quantified progress and a stated cap', () => {
    state.overview = overview({
      habits: [],
      candidates: [
        { key: 'email+contact', observed_days: 3, required_days: 4 },
        { key: 'calendar', observed_days: 4, required_days: 4 },
      ],
      candidates_more: 2,
    });
    renderSection();
    expect(screen.getByText('settings.habits.observing_title')).toBeInTheDocument();
    expect(screen.getByText('email + contact')).toBeInTheDocument();
    // Below the published gate: a real progressbar with backend values.
    const bar = screen.getByRole('progressbar', { name: 'settings.habits.candidate_aria' });
    expect(bar).toHaveAttribute('aria-valuenow', '3');
    expect(bar).toHaveAttribute('aria-valuemax', '4');
    // At the gate: the consistency-forming state, never a fake 100% claim.
    expect(screen.getByText('settings.habits.candidate_forming')).toBeInTheDocument();
    // The cap is stated, never silent (ADR-185 doctrine).
    expect(screen.getByText('settings.habits.candidates_more')).toBeInTheDocument();
  });

  it('no candidates section when nothing is under observation', () => {
    renderSection();
    expect(screen.queryByText('settings.habits.observing_title')).not.toBeInTheDocument();
  });

  it('the heatmap shows where activity concentrates even on a none verdict', () => {
    const bins = Array<number>(24).fill(0);
    bins[21] = 0.6;
    state.overview = overview({
      profile: {
        computed_at: '2026-08-05T04:10:00Z',
        weekday: profileClass({ verdict: 'none', n_eff: 20, bin_presence: bins }),
        weekend: profileClass(),
        active_days_fraction: 0.7,
        sparse: false,
      },
      habits: [],
    });
    renderSection();
    // One heatmap for the weekday class (weekend bins are all zero → none).
    const maps = screen.getAllByRole('img', { name: 'settings.habits.heatmap_aria' });
    expect(maps).toHaveLength(1);
    expect(maps[0].children).toHaveLength(24);
    // Each slot names its hour on hover; the axis anchors the reading
    // (owner screenshot feedback: bars without hours were unreadable).
    expect(maps[0].children[21]).toHaveAttribute('title', '21:00');
    expect(screen.getAllByText('00')).toHaveLength(1);
    expect(screen.getAllByText('12')).toHaveLength(1);
    expect(screen.getAllByText('24')).toHaveLength(1);
  });

  it('the profile caption quantifies active days beside the compute date', () => {
    renderSection(); // default overview: computed_at set, active_days_fraction 0.85
    expect(screen.getByText(/settings\.habits\.active_days_caption/)).toBeInTheDocument();
  });

  it('no heatmap when there is no presence at all', () => {
    state.overview = overview({
      profile: {
        computed_at: null,
        weekday: profileClass({ verdict: 'insufficient' }),
        weekend: profileClass({ verdict: 'insufficient', required_n_eff: 6 }),
        active_days_fraction: 0,
        sparse: false,
      },
      habits: [],
    });
    renderSection();
    expect(
      screen.queryByRole('img', { name: 'settings.habits.heatmap_aria' })
    ).not.toBeInTheDocument();
  });

  it('a transient load failure offers a retry instead of vanishing', () => {
    state.loadError = true;
    renderSection();
    fireEvent.click(screen.getByRole('button', { name: /common\.retry/ }));
    expect(refetch).toHaveBeenCalled();
  });
});

describe('formatWindow', () => {
  it('formats a plain window', () => {
    expect(formatWindow({ start_hour: 8, end_hour: 10, presence: 0.9 })).toBe('08:00–10:00');
  });

  it('keeps a midnight-wrapping window honest', () => {
    expect(formatWindow({ start_hour: 22, end_hour: 1, presence: 0.5 })).toBe('22:00–01:00');
  });
});
