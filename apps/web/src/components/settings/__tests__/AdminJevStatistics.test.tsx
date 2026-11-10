/**
 * The JEV screen's statistics (ADR-374): the share a threshold concludes, read from the
 * buckets as the slider moves; a window with no decision says so; an observer's verdicts
 * stand beside what its extractor proposed; every figure carries a name.
 *
 * The i18n stub here renders interpolations (`key {json}`): the figures ARE the
 * interpolated values, and the global stub would echo the key alone.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';
import { fireEvent } from '@testing-library/react';
import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import apiClient from '@/lib/api-client';
import type {
  JevGateStatistics,
  JevSettings,
  JevStatisticsResponse,
  JevUsageStatistics,
  JevUsageStatus,
} from '@/types/jev';
import AdminJevSection from '../AdminJevSection';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: 'en' },
  }),
}));

const endpoint = '/admin/llm-config/jev';
const statisticsEndpoint = '/admin/llm-config/jev/statistics?days=30';
const PREFIX = 'settings.admin.jev.statistics';

let chartBounds: MockInstance<HTMLElement['getBoundingClientRect']>;
beforeEach(() => {
  vi.restoreAllMocks();
  const original = HTMLElement.prototype.getBoundingClientRect;
  chartBounds = vi
    .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: HTMLElement): DOMRect {
      return this.classList.contains('recharts-responsive-container')
        ? new DOMRect(0, 0, 640, 320)
        : original.call(this);
    });
});
afterEach(() => chartBounds.mockRestore());

function emailStatus(): JevUsageStatus {
  return {
    usage: 'email_classification',
    label_key: 'settings.admin.jev.usages.email_classification',
    llm_type: 'jev_email_classification',
    enabled: true,
    effective: true,
    readiness: 'ready',
    qualified: true,
    gates: [
      {
        key: 'priority',
        kind: 'choice_concentration',
        scope: 'each',
        default: 0.8,
        minimum: 0.5,
        maximum: 1,
        value: 0.8,
      },
    ],
  };
}

function observerStatus(): JevUsageStatus {
  return {
    usage: 'observe_memory',
    label_key: 'settings.admin.jev.usages.observe_memory',
    llm_type: 'jev_observe_memory',
    enabled: true,
    effective: true,
    readiness: 'ready',
    qualified: true,
    gates: [],
  };
}

function buckets(entries: Record<number, number>): number[] {
  const list = new Array<number>(101).fill(0);
  for (const [bucket, count] of Object.entries(entries)) list[Number(bucket)] = count;
  return list;
}

function priority(entries: Record<number, number>): JevGateStatistics {
  return {
    key: 'priority',
    kind: 'choice_concentration',
    threshold: 0.8,
    buckets: buckets(entries),
  };
}

function usageStatistics(over: Partial<JevUsageStatistics>): JevUsageStatistics {
  return {
    usage: 'email_classification',
    calls: 0,
    cost_eur: 0,
    latency_p50_ms: null,
    outcomes: {},
    gates: [],
    agreement: null,
    ...over,
  };
}

function serve(
  usages: JevUsageStatus[],
  stats: JevUsageStatistics[] | Error
): MockInstance<typeof apiClient.get> {
  const settings: JevSettings = { enabled: true, usages };
  const response: JevStatisticsResponse | Error =
    stats instanceof Error ? stats : { days: 30, since: '2026-10-10', usages: stats };
  return vi.spyOn(apiClient, 'get').mockImplementation(async requested => {
    if (requested === endpoint) return settings;
    if (requested === statisticsEndpoint) {
      if (response instanceof Error) throw response;
      return response;
    }
    throw new Error(`Unexpected request: ${requested}`);
  });
}

describe('JEV statistics', () => {
  it('states the share the stored threshold concludes, read from the buckets', async () => {
    serve([emailStatus()], [usageStatistics({ gates: [priority({ 79: 1, 80: 3 })] })]);
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText(/settings\.admin\.jev\.thresholds\.toggle/));
    expect(await screen.findByText(/"share":"75%"/)).toHaveTextContent('"count":4');
  });

  it('follows the slider before anything is saved', async () => {
    serve([emailStatus()], [usageStatistics({ gates: [priority({ 79: 1, 80: 3 })] })]);
    vi.spyOn(apiClient, 'patch').mockReturnValue(new Promise(() => {}));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText(/settings\.admin\.jev\.thresholds\.toggle/));
    const slider = await screen.findByRole('slider', {
      name: /settings\.admin\.jev\.thresholds\.sliderLabel/,
    });
    slider.focus();
    fireEvent.keyDown(slider, { key: 'ArrowLeft' });
    // At 0.79 the judgement in bucket 79 concludes too: four of four.
    expect(await screen.findByText(/"share":"100%"/)).toBeInTheDocument();
  });

  it('says a gate judged nothing rather than drawing an empty chart', async () => {
    serve([emailStatus()], [usageStatistics({ gates: [priority({})] })]);
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText(/settings\.admin\.jev\.thresholds\.toggle/));
    expect(await screen.findByText(`${PREFIX}.noJudgement`)).toBeInTheDocument();
    expect(screen.queryByText(`${PREFIX}.distribution`)).not.toBeInTheDocument();
  });

  it('names the distribution figure of a gate once unfolded', async () => {
    serve([emailStatus()], [usageStatistics({ gates: [priority({ 80: 3 })] })]);
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText(/settings\.admin\.jev\.thresholds\.toggle/));
    await user.click(await screen.findByText(`${PREFIX}.distribution`));
    expect(screen.getByRole('figure', { name: `${PREFIX}.chartConfidence` })).toBeInTheDocument();
  });

  it('says a window without decision has none, and names the outcome figure when it has', async () => {
    serve(
      [emailStatus(), { ...emailStatus(), usage: 'event_classification', gates: [] }],
      [
        usageStatistics({ calls: 0 }),
        usageStatistics({
          usage: 'event_classification',
          calls: 4,
          cost_eur: 0.0012,
          latency_p50_ms: 180,
          outcomes: { classified: 3, uncertain: 1 },
        }),
      ]
    );
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    const folds = await screen.findAllByText(/settings\.admin\.jev\.statistics\.toggle/);
    await user.click(folds[0]);
    expect(await screen.findByText(`${PREFIX}.noDecision`)).toBeInTheDocument();
    await user.click(folds[1]);
    expect(screen.getByRole('figure', { name: `${PREFIX}.outcomesTitle` })).toBeInTheDocument();
    expect(screen.getByText(/"value":"180"/)).toBeInTheDocument();
  });

  it('shows an observer’s verdicts beside what its extractor proposed', async () => {
    serve(
      [observerStatus()],
      [
        usageStatistics({
          usage: 'observe_memory',
          calls: 7,
          outcomes: { observed: 7 },
          agreement: [
            { verdict: 'empty', bucket: 90, proposed: false, count: 2 },
            { verdict: 'empty', bucket: 80, proposed: false, count: 1 },
            { verdict: 'empty', bucket: 95, proposed: true, count: 1 },
            { verdict: 'useful', bucket: 95, proposed: true, count: 3 },
          ],
        }),
      ]
    );
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    await user.click(await screen.findByText(/settings\.admin\.jev\.statistics\.toggle/));
    const table = await screen.findByRole('table', {
      name: new RegExp(`${PREFIX}.agreementTitle`),
    });
    const empty = within(table).getByRole('row', { name: new RegExp(`${PREFIX}.verdicts.empty`) });
    expect(
      within(empty)
        .getAllByRole('cell')
        .map(cell => cell.textContent)
    ).toEqual(['1', '3']);
    const useful = within(table).getByRole('row', {
      name: new RegExp(`${PREFIX}.verdicts.useful`),
    });
    expect(
      within(useful)
        .getAllByRole('cell')
        .map(cell => cell.textContent)
    ).toEqual(['3', '0']);
  });

  it('says the statistics could not be read and keeps every switch', async () => {
    serve([emailStatus()], new Error('unavailable'));
    const { user } = renderWithProviders(<AdminJevSection lng="en" />);
    expect(await screen.findByRole('switch', { name: emailStatus().label_key })).toBeChecked();
    await user.click(await screen.findByText(/settings\.admin\.jev\.statistics\.toggle/));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(`${PREFIX}.error`));
  });
});
