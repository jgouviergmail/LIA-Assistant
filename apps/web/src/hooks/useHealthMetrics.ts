import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Aggregation period matching backend HEALTH_METRICS_PERIODS constant.
 */
export type HealthMetricsPeriod = 'hour' | 'day' | 'week' | 'month' | 'year';

/**
 * Sample kind discriminator matching backend HEALTH_METRICS_KINDS.
 */
export type HealthMetricsKind = 'heart_rate' | 'steps';

/**
 * One aggregated bucket as returned by /health-metrics/aggregate.
 */
export interface HealthMetricsAggregatePoint {
  bucket: string;
  heart_rate_avg: number | null;
  heart_rate_min: number | null;
  heart_rate_max: number | null;
  steps_total: number | null;
  has_data: boolean;
}

export interface HealthMetricsPeriodAverages {
  heart_rate_avg: number | null;
  steps_per_day_avg: number | null;
}

export interface HealthMetricsAggregateResponse {
  period: HealthMetricsPeriod;
  from_ts: string;
  to_ts: string;
  points: HealthMetricsAggregatePoint[];
  averages: HealthMetricsPeriodAverages;
}

/**
 * Ingestion token row (no raw secret).
 */
export interface HealthMetricsTokenRow {
  id: string;
  token_prefix: string;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface HealthMetricsTokenListResponse {
  tokens: HealthMetricsTokenRow[];
}

/**
 * Response returned once after creating a token — `token` is the raw value
 * and will never be returned again.
 */
export interface HealthMetricsTokenCreateResponse {
  id: string;
  token: string;
  token_prefix: string;
  label: string | null;
  created_at: string;
}

export interface HealthMetricsDeleteResponse {
  scope: 'all' | 'kind';
  kind: HealthMetricsKind | null;
  affected_rows: number;
}

/**
 * Hook for the Health Metrics feature (ingestion tokens + aggregated charts).
 *
 * Consumes:
 *   GET    /api/v1/health-metrics/aggregate
 *   GET    /api/v1/health-metrics/tokens
 *   POST   /api/v1/health-metrics/tokens
 *   DELETE /api/v1/health-metrics/tokens/{id}
 *   DELETE /api/v1/health-metrics
 *   DELETE /api/v1/health-metrics/all
 */
export function useHealthMetrics(period: HealthMetricsPeriod = 'day') {
  // Aggregated chart data
  const {
    data: aggregate,
    loading: aggregateLoading,
    error: aggregateError,
    refetch: refetchAggregate,
  } = useApiQuery<HealthMetricsAggregateResponse>('/health-metrics/aggregate', {
    componentName: 'useHealthMetrics',
    params: { period },
    deps: [period],
  });

  // Token listing
  const {
    data: tokensData,
    loading: tokensLoading,
    refetch: refetchTokens,
  } = useApiQuery<HealthMetricsTokenListResponse>('/health-metrics/tokens', {
    componentName: 'useHealthMetrics',
    initialData: { tokens: [] },
  });

  const { mutate: createTokenMutate, loading: creatingToken } = useApiMutation<
    { label?: string },
    HealthMetricsTokenCreateResponse
  >({
    method: 'POST',
    componentName: 'useHealthMetrics',
  });

  const { mutate: revokeTokenMutate } = useApiMutation({
    method: 'DELETE',
    componentName: 'useHealthMetrics',
  });

  const { mutate: deleteKindMutate, loading: deletingKind } = useApiMutation<
    undefined,
    HealthMetricsDeleteResponse
  >({
    method: 'DELETE',
    componentName: 'useHealthMetrics',
  });

  const { mutate: deleteAllMutate, loading: deletingAll } = useApiMutation<
    undefined,
    HealthMetricsDeleteResponse
  >({
    method: 'DELETE',
    componentName: 'useHealthMetrics',
  });

  // v1.17.2 — assistant toggle
  const {
    mutate: updateAgentsPreferenceMutate,
    loading: updatingAgentsPreference,
  } = useApiMutation<
    { health_metrics_agents_enabled: boolean },
    { health_metrics_agents_enabled: boolean; message: string }
  >({
    method: 'PATCH',
    componentName: 'useHealthMetrics',
  });

  const createToken = useCallback(
    async (label?: string): Promise<HealthMetricsTokenCreateResponse | null> => {
      const result = await createTokenMutate('/health-metrics/tokens', { label });
      if (result) {
        await refetchTokens();
      }
      return result ?? null;
    },
    [createTokenMutate, refetchTokens]
  );

  const revokeToken = useCallback(
    async (tokenId: string) => {
      await revokeTokenMutate(`/health-metrics/tokens/${tokenId}`);
      await refetchTokens();
    },
    [revokeTokenMutate, refetchTokens]
  );

  const deleteKind = useCallback(
    async (kind: HealthMetricsKind) => {
      const result = await deleteKindMutate(`/health-metrics?kind=${kind}`);
      await refetchAggregate();
      return result;
    },
    [deleteKindMutate, refetchAggregate]
  );

  const deleteAll = useCallback(async () => {
    const result = await deleteAllMutate('/health-metrics/all');
    await refetchAggregate();
    return result;
  }, [deleteAllMutate, refetchAggregate]);

  const updateAgentsEnabled = useCallback(
    async (enabled: boolean) => {
      return updateAgentsPreferenceMutate('/auth/me/health-metrics-agents-preference', {
        health_metrics_agents_enabled: enabled,
      });
    },
    [updateAgentsPreferenceMutate]
  );

  return {
    // Data
    aggregate,
    tokens: tokensData?.tokens ?? [],

    // Loading states
    isLoading: aggregateLoading || tokensLoading,
    error: aggregateError,
    isCreatingToken: creatingToken,
    isDeleting: deletingKind || deletingAll,
    isUpdatingAgentsPreference: updatingAgentsPreference,

    // Actions
    createToken,
    revokeToken,
    deleteKind,
    deleteAll,
    updateAgentsEnabled,

    // Refetch
    refetchAggregate,
    refetchTokens,
  };
}
