/**
 * PsycheHistory — the mood/emotion history panel.
 *
 * The real Recharts charts receive a measured container under JSDOM. What is
 * pinned here is the logic around them — the query is only fired when the panel
 * is open, each time range asks for its own window and limit, reset snapshots
 * are markers rather than data points, and the three display states
 * (loading / empty / charted) are mutually exclusive.
 */

import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from 'vitest';

import { renderWithProviders, screen, waitFor, act } from '@/__tests__/test-utils';
import { publishApplicationResources } from '@/lib/application-resources';
import { dataQuery, loadingQuery, errorQuery } from '@/__tests__/api-mocks';
import type { PsycheHistoryEntry } from '@/types/psyche';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApplicationAccountQuery', () => ({ useApplicationAccountQuery: useApiQuery }));

import { PsycheHistory } from '../PsycheHistory';
import { toPsycheHistoryData } from '../psyche-history-data';

// ResponsiveContainer reads this boundary before observing it. Give only the
// chart container a measured JSDOM box; the real Recharts SVG still renders.
let chartBounds: MockInstance<HTMLElement['getBoundingClientRect']>;

beforeEach(() => {
  const originalBounds = HTMLElement.prototype.getBoundingClientRect;
  chartBounds = vi
    .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: HTMLElement): DOMRect {
      return this.classList.contains('recharts-responsive-container')
        ? new DOMRect(0, 0, 640, 320)
        : originalBounds.call(this);
    });
});

afterEach(() => chartBounds.mockRestore());

function entry(over: Partial<PsycheHistoryEntry> = {}): PsycheHistoryEntry {
  return {
    id: 'p1',
    snapshot_type: 'periodic',
    mood_pleasure: 0.4,
    mood_arousal: 0.1,
    mood_dominance: -0.2,
    dominant_emotion: 'curiosity',
    relationship_stage: 'companion',
    trait_snapshot: {
      emotion_intensity: 0.6,
      relationship_depth: 0.3,
      relationship_warmth: 0.5,
      relationship_trust: 0.4,
      drive_curiosity: 0.7,
      drive_engagement: 0.2,
    },
    created_at: '2026-07-18T09:00:00Z',
    ...over,
  };
}

function render(isOpen = true) {
  return renderWithProviders(<PsycheHistory lng="fr" isOpen={isOpen} />);
}

/** The endpoint the panel last asked for. */
function lastEndpoint(): string {
  const calls = useApiQuery.mock.calls;
  return String(calls[calls.length - 1][0]);
}

const EMPTY = 'psyche.history.empty';

beforeEach(() => {
  vi.clearAllMocks();
  useApiQuery.mockReturnValue(dataQuery<PsycheHistoryEntry[]>([]));
});

describe('PsycheHistory — fetch gating', () => {
  it('rereads the current open history after a native reset and ignores another owner', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    useApiQuery.mockReturnValue({
      ...dataQuery<PsycheHistoryEntry[]>([]),
      ownerId: 'one',
      refetch,
    });
    const { unmount } = render();
    act(() => publishApplicationResources('two', new Set(['psyche'])));
    expect(refetch).not.toHaveBeenCalled();
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    unmount();
    act(() => publishApplicationResources('one', new Set(['psyche'])));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
  it('does not query while the panel is closed', () => {
    render(false);
    expect(useApiQuery.mock.calls[0][2]).toBe(false);
  });

  it('queries the last 7 days by default', () => {
    render();
    expect(lastEndpoint()).toBe('/psyche/history?limit=200&hours=168');
    expect(useApiQuery.mock.calls[0][2]).toBe(true);
  });

  it.each([
    ['24h', 'limit=100&hours=24'],
    ['30d', 'limit=300&hours=720'],
    ['90d', 'limit=500&hours=2160'],
  ])('asks for its own window when %s is picked', async (range, expected) => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `psyche.history.tabs.${range}` }));
    await waitFor(() => expect(lastEndpoint()).toBe(`/psyche/history?${expected}`));
  });
});

describe('PsycheHistory — display states', () => {
  it('announces the load in progress', () => {
    useApiQuery.mockReturnValue(loadingQuery<PsycheHistoryEntry[]>());
    render();
    expect(screen.getByText('psyche.history.loading')).toBeInTheDocument();
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
  });

  it('says the period holds nothing', () => {
    render();
    expect(screen.getByText(EMPTY)).toBeInTheDocument();
    expect(screen.queryByText('psyche.history.loading')).not.toBeInTheDocument();
  });

  it('charts the period once it holds snapshots', () => {
    useApiQuery.mockReturnValue(dataQuery([entry(), entry({ id: 'p2' })]));
    render();
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
    expect(document.querySelector('svg.recharts-surface')).toBeInTheDocument();
  });

  it('accepts the emotion map the backend actually sends', () => {
    // `trait_snapshot.active_emotions` is a `dict[str, float]`, not a scalar:
    // the entry only type-checks since the contract was corrected. The chart
    // container is measured in this fixture, so the real payload feeds the
    // transform without blowing up and reaches the actual chart renderer.
    useApiQuery.mockReturnValue(
      dataQuery([
        entry({
          trait_snapshot: {
            emotion_intensity: 0.6,
            active_emotions: { curiosity: 0.62, serenity: 0.31 },
            relationship_depth: 0.3,
          },
        }),
        entry({ id: 'p2' }),
      ])
    );
    render();
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
  });

  it('treats reset snapshots as markers, not as data points', () => {
    // A period made only of resets has nothing to plot.
    useApiQuery.mockReturnValue(
      dataQuery([
        entry({ id: 'r1', snapshot_type: 'reset_full' }),
        entry({ id: 'r2', snapshot_type: 'reset_soft' }),
      ])
    );
    render();
    expect(screen.getByText(EMPTY)).toBeInTheDocument();
  });
});

describe('PsycheHistory — one temporal coordinate', () => {
  it.each([
    ['the same recorded instant', '2026-07-18T09:00:00Z', '2026-07-18T09:00:00Z'],
    [
      'API microseconds within one millisecond',
      '2026-07-18T09:00:00.123900Z',
      '2026-07-18T09:00:00.123400Z',
    ],
  ])('keeps both snapshots and one axis tick for %s', (_case, newer, older) => {
    const entries = [
      entry({ id: 'p1', created_at: newer, mood_pleasure: 0.4 }),
      entry({ id: 'p2', created_at: older, mood_pleasure: -0.4 }),
    ];
    const { points } = toPsycheHistoryData(entries);
    expect(points).toHaveLength(2);
    expect(points[0].time).toBe(points[1].time);
    useApiQuery.mockReturnValue(dataQuery(entries));

    // The spy calls through: a duplicate React key remains visible in stderr.
    const errors = vi.spyOn(console, 'error');
    try {
      render();
      const svg = document.querySelector('svg.recharts-surface');
      expect(svg).toBeInTheDocument();
      const curve = svg?.querySelector('path.recharts-line-curve')?.getAttribute('d') ?? '';
      const coordinates = curve.match(/[-+]?\d*\.?\d+(?:e[-+]?\d+)?/gi)?.map(Number) ?? [];
      expect(coordinates).toHaveLength(4);
      expect(coordinates[0]).toBe(coordinates[2]);
      expect(coordinates[1]).not.toBe(coordinates[3]);
      expect(
        svg?.querySelectorAll('.recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-label')
      ).toHaveLength(1);
      expect(errors).not.toHaveBeenCalled();
    } finally {
      errors.mockRestore();
    }
  });
});

describe('PsycheHistory — chart tabs', () => {
  beforeEach(() => {
    useApiQuery.mockReturnValue(dataQuery([entry(), entry({ id: 'p2' })]));
  });

  it.each(['Emotions', 'Relationship', 'Drives', 'Pad'])('renders the %s chart', async tab => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: `psyche.history.chart${tab}` }));
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
  });
});

describe('PsycheHistory — accessible controls and failures', () => {
  it('announces exactly one selected range and chart type', async () => {
    const { user } = render();
    expect(screen.getByRole('button', { name: 'psyche.history.tabs.7d' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await user.click(screen.getByRole('button', { name: 'psyche.history.chartDrives' }));
    expect(screen.getByRole('button', { name: 'psyche.history.chartDrives' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: 'psyche.history.chartPad' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });
  it('distinguishes a read failure from an empty period and offers retry', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    useApiQuery.mockReturnValue(errorQuery<PsycheHistoryEntry[]>('offline', { refetch }));
    const { user } = render();
    expect(screen.getByRole('alert')).toHaveTextContent('psyche.history.loadError');
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'psyche.history.retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
  it('keeps populated charts present while refreshing', () => {
    useApiQuery.mockReturnValue(dataQuery([entry()], { loading: true }));
    render();
    expect(screen.getByRole('region', { name: /psyche.history.chartPad/ })).toHaveAttribute(
      'aria-busy',
      'true'
    );
  });
});

describe('PsycheHistory — chart data contract', () => {
  it('keeps absent metrics absent, sorts immutable data by exact timestamp and excludes reset points', () => {
    const entries = [
      entry({ id: 'late', created_at: '2026-07-18T09:00:40Z', trait_snapshot: null }),
      entry({ id: 'reset', created_at: '2026-07-18T09:00:30Z', snapshot_type: 'reset_soft' }),
      entry({ id: 'early', created_at: '2026-07-18T09:00:10Z' }),
      entry({ id: 'invalid', created_at: 'invalid' }),
    ];
    Object.freeze(entries);
    const { points, resets } = toPsycheHistoryData(entries);
    expect(points).toHaveLength(2);
    expect(points[0].time).toBe(Date.parse('2026-07-18T09:00:10Z'));
    expect(points[1].time).toBe(Date.parse('2026-07-18T09:00:40Z'));
    expect(points[1].depth).toBeNull();
    expect(points[1].emotionIntensity).toBeNull();
    expect(resets).toEqual([{ time: Date.parse('2026-07-18T09:00:30Z'), type: 'reset_soft' }]);
    expect(entries[0].id).toBe('late');
    useApiQuery.mockReturnValue(dataQuery(entries));
    render();
    expect(
      document.querySelectorAll('.recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-label')
        .length
    ).toBeGreaterThan(1);
  });
  it('preserves all emotion series, relationship and drives as actual percentages', () => {
    const { points, emotions } = toPsycheHistoryData([
      entry({
        trait_snapshot: {
          active_emotions: { joy: 0.7, serenity: 0.2 },
          drive_curiosity: 0.66,
          drive_engagement: 0.75,
          relationship_depth: 0,
          relationship_trust: 0.85,
          relationship_warmth: 0.4,
          emotion_intensity: 0.7,
        },
      }),
    ]);
    expect(points[0]).toMatchObject({
      P: 40,
      A: 10,
      D: -20,
      depth: 0,
      trust: 85,
      warmth: 40,
      curiosity: 66,
      engagement: 75,
      emotionIntensity: 70,
      emo_joy: 70,
      emo_serenity: 20,
    });
    expect(emotions).toEqual(['emo_joy', 'emo_serenity']);
  });
});

describe('PsycheHistory — explicit reset refresh', () => {
  it('refreshes the already open history after a reset, without a read on mount', async () => {
    const refetch = vi.fn().mockResolvedValue(undefined);
    useApiQuery.mockReturnValue(dataQuery<PsycheHistoryEntry[]>([], { refetch }));
    const { rerender } = renderWithProviders(<PsycheHistory lng="fr" isOpen refreshKey={0} />);
    expect(refetch).not.toHaveBeenCalled();
    rerender(<PsycheHistory lng="fr" isOpen refreshKey={1} />);
    await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1));
    rerender(<PsycheHistory lng="fr" isOpen={false} refreshKey={2} />);
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe('PsycheHistory — failed follow-up reads', () => {
  it('handles rejected retry and reset refresh promises through the query error state', async () => {
    let reads = 0;
    const refetch = async () => {
      reads += 1;
      throw new Error('offline');
    };
    useApiQuery.mockReturnValue(errorQuery<PsycheHistoryEntry[]>('offline', { refetch }));
    const { user, rerender } = renderWithProviders(
      <PsycheHistory lng="fr" isOpen refreshKey={0} />
    );
    await user.click(screen.getByRole('button', { name: 'psyche.history.retry' }));
    await waitFor(() => expect(reads).toBe(1));
    rerender(<PsycheHistory lng="fr" isOpen refreshKey={1} />);
    await waitFor(() => expect(reads).toBe(2));
    expect(screen.getByRole('alert')).toHaveTextContent('psyche.history.loadError');
  });
});
