/**
 * RegisterCharts — a figure is a claim, so it must be checkable (ADR-263).
 *
 * The properties here are the register doctrines applied to a chart:
 *
 * - the exact total sits beside the bars, because the server folds a long tail
 *   into « other » and a reader must be able to see that they add up (ADR-185);
 * - an empty series SAYS it is empty — a blank card reads as a broken one, and
 *   for the integrity card empty is the good news;
 * - labels are rendered into the reader's language, and one the vocabulary does
 *   not know is shown AS STORED rather than blanked;
 * - one component serves both audiences, so the reader's screen and the
 *   operator's cannot disagree about what a series means.
 *
 * `recharts` measures its container, which jsdom reports as zero — so the bars
 * themselves are not asserted here. What is asserted is everything around them,
 * which is where the claims live.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RegisterCharts } from '@/components/effects/RegisterCharts';
import type { RegisterStatistics } from '@/hooks/useRegisterStatistics';

const dictionary: Record<string, string> = {
  'registers.charts.loading': 'Loading the figures',
  'registers.charts.empty': 'Nothing in this period.',
  'registers.charts.error': 'The figures could not be computed.',
  'registers.charts.activity.title': 'Activity per day',
  'registers.charts.turns_outcome.title': 'How turns ended',
  'registers.charts.actions_status.title': 'Actions by outcome',
  'registers.charts.consultations_domain.title': 'Consultations by domain',
  'registers.charts.calls_model.title': 'Calls per model',
  'registers.charts.calls_node.title': 'Calls per graph step',
  'registers.charts.tokens_model.title': 'Tokens per model',
  'registers.charts.latency.title': 'Average latency per tool',
  'registers.charts.turns_mode.title': 'Execution mode',
  'registers.charts.integrity.title': 'Gaps in the record',
  'registers.charts.integrity.empty': 'No gaps: the record is complete.',
  'registers.charts.outcome.answered': 'Answered',
  'registers.charts.integrity_kind.chain_broken': 'Broken chain',
  'registers.charts.badge.count': 'Total {{value}}',
  'registers.charts.badge.stacked': 'Total {{value}}',
  'registers.charts.badge.average': 'Average {{value}}',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; value?: string }) => {
      const template = dictionary[key] ?? options?.defaultValue ?? key;
      return options?.value === undefined
        ? template
        : template.replace('{{value}}', options.value);
    },
    i18n: { language: 'en' },
  }),
}));

const state = {
  statistics: undefined as RegisterStatistics | undefined,
  loading: false,
  error: null as Error | null,
  refetch: vi.fn(),
};

const seen: unknown[] = [];
vi.mock('@/hooks/useRegisterStatistics', () => ({
  useRegisterStatistics: (options: unknown) => {
    seen.push(options);
    return state;
  },
}));

const empty = { slices: [], total: 0, kind: 'count' as const };

function figures(overrides: Partial<RegisterStatistics> = {}): RegisterStatistics {
  return {
    calls_by_model: empty,
    calls_by_node: empty,
    tokens_by_model: empty,
    consultations_by_domain: empty,
    consultation_latency_by_tool: empty,
    actions_by_status: empty,
    turns_by_outcome: empty,
    turns_by_mode: empty,
    integrity_by_kind: empty,
    activity_by_day: empty,
    ...overrides,
  };
}

beforeEach(() => {
  state.statistics = figures();
  state.loading = false;
  state.error = null;
  seen.length = 0;
});

describe('RegisterCharts', () => {
  it('draws every record, not a selection of them', () => {
    render(<RegisterCharts />);

    for (const title of [
      'Activity per day',
      'How turns ended',
      'Actions by outcome',
      'Consultations by domain',
      'Calls per model',
      'Calls per graph step',
      'Tokens per model',
      'Average latency per tool',
      'Execution mode',
      'Gaps in the record',
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it('shows the EXACT total beside the bars it must add up to', () => {
    // The server folds a long tail into « other »; without the total a reader
    // could not check the sum, and a chart nobody can check is decoration.
    state.statistics = figures({
      calls_by_model: {
        slices: [{ label: 'gpt-5-mini', count: 40, secondary: 0 }],
        total: 137,
        kind: 'count' as const,
      },
    });

    render(<RegisterCharts />);

    expect(screen.getByText('Total 137')).toBeInTheDocument();
  });

  it('says an empty period is empty rather than showing a blank card', () => {
    render(<RegisterCharts />);

    expect(screen.getAllByText('Nothing in this period.').length).toBeGreaterThan(0);
  });

  it('tells the reader that NO gaps is the good news', () => {
    // Every other card gets the neutral sentence; this one deserves its own.
    render(<RegisterCharts />);

    expect(screen.getByText('No gaps: the record is complete.')).toBeInTheDocument();
  });

  it('stops saying « empty » on the card that has data', () => {
    // Scoped to the CARD: every other one is legitimately empty in this
    // fixture, so an unscoped query would pass whatever the component did.
    state.statistics = figures({
      turns_by_outcome: {
        slices: [{ label: 'answered', count: 3, secondary: 0 }],
        total: 3,
        kind: 'count' as const,
      },
    });

    render(<RegisterCharts />);
    const card = screen.getByText('How turns ended').closest('div[class*="rounded"]');

    expect(card).not.toBeNull();
    expect(card?.textContent).not.toContain('Nothing in this period.');
    expect(card?.textContent).toContain('3');
  });

  it('holds the page geometry while the figures load', () => {
    state.loading = true;
    state.statistics = undefined;

    render(<RegisterCharts />);

    expect(screen.getAllByRole('status', { name: 'Loading the figures' }).length).toBe(4);
  });

  it('says so when the figures could not be computed', () => {
    state.error = new Error('boom');

    render(<RegisterCharts />);

    expect(screen.getByText('The figures could not be computed.')).toBeInTheDocument();
  });

  it('passes the ADMIN scope straight through, and nothing by default', () => {
    // One component, two audiences: the scope is a parameter of the query, and
    // a reader's own view must not be able to name an account at all.
    render(<RegisterCharts />);
    render(<RegisterCharts admin userIds={['user-a', 'user-b']} />);

    expect(seen[0]).toEqual({});
    expect(seen[seen.length - 1]).toEqual({ admin: true, userIds: ['user-a', 'user-b'] });
  });
});
