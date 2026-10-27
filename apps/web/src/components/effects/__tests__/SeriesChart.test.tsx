/**
 * SeriesChart — a badge is a claim about the bars beside it (ADR-263/ADR-185).
 *
 * Two series do not draw plain counts, and each wore a badge a reader could not
 * check against them: the tokens chart STACKS two measures on one bar, and the
 * latency chart draws MEANS, which never sum. The wording now comes from the
 * series' own `kind`, so a chart added tomorrow cannot label it wrongly.
 *
 * The fixture supplies a measured container to the real Recharts renderer.
 * The surrounding claims and the presence of its SVG are asserted together.
 */

import { describe, expect, it, vi, beforeEach, afterEach, type MockInstance } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SeriesChart } from '@/components/effects/SeriesChart';
import type { StatisticsSeries } from '@/hooks/useRegisterStatistics';

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

const dictionary: Record<string, string> = {
  'registers.charts.badge.count': 'Total {{value}}',
  'registers.charts.badge.stacked': 'Total {{value}}',
  'registers.charts.badge.average': 'Average {{value}}',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; value?: string }) => {
      const template = dictionary[key] ?? options?.defaultValue ?? key;
      return options?.value === undefined ? template : template.replace('{{value}}', options.value);
    },
    i18n: { language: 'en' },
  }),
}));

function series(over: Partial<StatisticsSeries> = {}): StatisticsSeries {
  return { slices: [], total: 0, kind: 'count', ...over };
}

function renderChart(over: Partial<StatisticsSeries>, unit?: string) {
  render(
    <SeriesChart
      title="A chart"
      series={series(over)}
      emptyLabel="Nothing here."
      countLabel="Calls"
      unit={unit}
    />
  );
}

describe('SeriesChart', () => {
  it('calls a count a TOTAL', () => {
    renderChart({ slices: [{ label: 'a', count: 3, secondary: 0 }], total: 3 });

    expect(screen.getByText('Total 3')).toBeInTheDocument();
    expect(document.querySelector('svg.recharts-surface')).toBeInTheDocument();
  });

  it('calls a mean an AVERAGE, never a total', () => {
    // 80 ms is the weighted mean, not a sum: labelling it « Total » would
    // invite the reader to add bars that never add up.
    renderChart(
      { slices: [{ label: 'x', count: 100, secondary: 0 }], total: 80, kind: 'average' },
      'ms'
    );

    expect(screen.getByText('Average 80 ms')).toBeInTheDocument();
    expect(screen.queryByText('Total 80 ms')).not.toBeInTheDocument();
  });

  it('states a stacked figure as the total of BOTH measures', () => {
    renderChart({
      slices: [{ label: 'gpt', count: 20, secondary: 10 }],
      total: 30,
      kind: 'stacked',
    });

    expect(screen.getByText('Total 30')).toBeInTheDocument();
  });

  it('carries the unit into the badge', () => {
    renderChart({ slices: [{ label: 'x', count: 1, secondary: 0 }], total: 42 }, 'ms');

    expect(screen.getByText('Total 42 ms')).toBeInTheDocument();
  });

  it('says an empty series is empty rather than drawing nothing', () => {
    renderChart({});

    expect(screen.getByText('Nothing here.')).toBeInTheDocument();
  });

  it('shows no badge at all while the series is unknown', () => {
    // Undefined is « not loaded yet », which is not the same claim as zero.
    render(
      <SeriesChart
        title="A chart"
        series={undefined}
        emptyLabel="Nothing here."
        countLabel="Calls"
      />
    );

    expect(screen.queryByText(/Total/)).not.toBeInTheDocument();
    expect(screen.getByText('Nothing here.')).toBeInTheDocument();
  });

  it('renders raw labels through the caller’s renderer', () => {
    render(
      <SeriesChart
        title="A chart"
        series={series({ slices: [{ label: 'raw', count: 1, secondary: 0 }], total: 1 })}
        emptyLabel="Nothing here."
        countLabel="Calls"
        renderLabel={label => `seen:${label}`}
      />
    );

    // The renderer must be applied, not bypassed — the domain vocabulary and
    // the collapsed node names both travel through it.
    expect(screen.getByText('Total 1')).toBeInTheDocument();
  });
});
