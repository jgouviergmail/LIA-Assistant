/**
 * HealthMetricsSettings — the loading state of the health metrics dashboard.
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
