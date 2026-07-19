/**
 * PsycheHistory — the mood/emotion history panel.
 *
 * The charts themselves are recharts declarative markup (a `ResponsiveContainer`
 * has no measurable size under jsdom, so its internals never paint): what is
 * pinned here is the logic around them — the query is only fired when the panel
 * is open, each time range asks for its own window and limit, reset snapshots
 * are markers rather than data points, and the three display states
 * (loading / empty / charted) are mutually exclusive.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { dataQuery, loadingQuery } from '@/__tests__/api-mocks';
import type { PsycheHistoryEntry } from '@/types/psyche';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

import { PsycheHistory } from '../PsycheHistory';

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
  it('does not query while the panel is closed', () => {
    render(false);
    expect(useApiQuery.mock.calls[0][1]).toMatchObject({ enabled: false });
  });

  it('queries the last 7 days by default', () => {
    render();
    expect(lastEndpoint()).toBe('/psyche/history?limit=200&hours=168');
    expect(useApiQuery.mock.calls[0][1]).toMatchObject({ enabled: true });
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
  });

  it('accepts the emotion map the backend actually sends', () => {
    // `trait_snapshot.active_emotions` is a `dict[str, float]`, not a scalar:
    // the entry only type-checks since the contract was corrected. The chart
    // internals never paint under jsdom, so what this pins is that the real
    // payload feeds the transform without blowing up and produces a chart.
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
