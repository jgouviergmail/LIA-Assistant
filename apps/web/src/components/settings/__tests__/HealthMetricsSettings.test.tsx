/**
 * HealthMetricsSettings — the loading state of the health metrics dashboard,
 * and the folds: the figures (statistics, then charts) open on arrival.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useHealthMetrics } = vi.hoisted(() => ({ useHealthMetrics: vi.fn() }));
vi.mock('@/hooks/useHealthMetrics', () => ({ useHealthMetrics }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { HealthMetricsSettings } from '../HealthMetricsSettings';
import type { useHealthMetrics as useHealthMetricsFn } from '@/hooks/useHealthMetrics';

type HealthHook = ReturnType<typeof useHealthMetricsFn>;

function hook(over: Partial<HealthHook> = {}) {
  return {
    aggregate: null,
    tokens: [],
    isLoading: false,
    isCreatingToken: false,
    isDeleting: false,
    isUpdatingAgentsPreference: false,
    createToken: vi.fn(),
    revokeToken: vi.fn(),
    deleteKind: vi.fn(),
    deleteAll: vi.fn(),
    updateAgentsEnabled: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u1', health_metrics_enabled: true },
    refreshUser: vi.fn(),
  });
});

describe('HealthMetricsSettings', () => {
  it('shows a loading indicator while metrics load', () => {
    useHealthMetrics.mockReturnValue(hook({ isLoading: true }));
    renderWithProviders(
      <HealthMetricsSettings lng="en" />
    );
    expect(screen.getAllByText('common.loading').length).toBeGreaterThan(0);
  });
});

describe('HealthMetricsSettings — folds', () => {
  const STATS = 'healthMetrics.stats.title';
  const CHARTS = 'healthMetrics.charts.title';

  function trigger(name: string) {
    return screen.getByRole('button', { name });
  }

  it('opens the statistics and the charts on arrival, the setup folds stay closed', () => {
    useHealthMetrics.mockReturnValue(hook());
    renderWithProviders(<HealthMetricsSettings lng="en" />);
    expect(trigger(STATS)).toHaveAttribute('aria-expanded', 'true');
    expect(trigger(CHARTS)).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('healthMetrics.stats.hrAvg')).toBeInTheDocument();
    for (const closed of [
      'healthMetrics.ingestion.title',
      'healthMetrics.agents.title',
      'healthMetrics.management.title',
    ]) {
      expect(trigger(closed)).toHaveAttribute('aria-expanded', 'false');
    }
  });

  it('puts the statistics above the charts', () => {
    useHealthMetrics.mockReturnValue(hook());
    renderWithProviders(<HealthMetricsSettings lng="en" />);
    const position = trigger(STATS).compareDocumentPosition(trigger(CHARTS));
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('still folds an open fold on click', async () => {
    useHealthMetrics.mockReturnValue(hook());
    const { user } = renderWithProviders(<HealthMetricsSettings lng="en" />);
    await user.click(trigger(STATS));
    expect(trigger(STATS)).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('healthMetrics.stats.hrAvg')).not.toBeInTheDocument();
  });

  it('paints every fold title icon in the theme colour', () => {
    useHealthMetrics.mockReturnValue(hook());
    renderWithProviders(<HealthMetricsSettings lng="en" />);
    for (const name of [STATS, CHARTS, 'healthMetrics.management.title']) {
      const icon = trigger(name).querySelector('svg');
      expect(icon).toHaveClass('text-primary');
      expect(icon).toHaveAttribute('aria-hidden', 'true');
    }
  });
});
