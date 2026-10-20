import { useCallback } from 'react';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';
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
  const aggregateQuery = useApplicationAccountQuery<HealthMetricsAggregateResponse>(
    `/health-metrics/aggregate?period=${period}`,
    'useHealthMetrics'
  );
  const {
    data: aggregate,
    loading: aggregateLoading,
    error: aggregateError,
    refetch: refetchAggregate,
    ownerId,
    isCurrent,
    setData: setAggregate,
  } = aggregateQuery;

  // Token listing
  const tokenQuery = useApplicationAccountQuery<HealthMetricsTokenListResponse>(
    '/health-metrics/tokens',
    'useHealthMetrics'
  );
  const {
    data: tokensData,
    loading: tokensLoading,
    refetch: refetchTokens,
    setData: setTokens,
  } = tokenQuery;
  const refreshHealth = useCallback(async () => {
    setAggregate(undefined);
    setTokens(undefined);
    await Promise.all([refetchAggregate(), refetchTokens()]);
  }, [setAggregate, setTokens, refetchAggregate, refetchTokens]);
  const releaseHealth = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'health_metrics', refreshHealth, releaseHealth);

  const { mutate: createTokenMutate, loading: creatingToken } = useApiMutation<
    { label?: string },
    HealthMetricsTokenCreateResponse
  >({
    method: 'POST',
    componentName: 'useHealthMetrics',
    retainResponse: false,
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
  const { mutate: updateAgentsPreferenceMutate, loading: updatingAgentsPreference } =
    useApiMutation<
      { health_metrics_agents_enabled: boolean },
      { health_metrics_agents_enabled: boolean; message: string }
    >({
      method: 'PATCH',
      componentName: 'useHealthMetrics',
    });

  const createToken = useCallback(
    async (label?: string): Promise<HealthMetricsTokenCreateResponse | null> => {
      if (!isCurrent()) return null;
      const result = await createTokenMutate('/health-metrics/tokens', { label });
      if (!isCurrent()) return null;
      if (result) {
        await refetchTokens();
      }
      return isCurrent() ? (result ?? null) : null;
    },
    [createTokenMutate, refetchTokens, isCurrent]
  );

  const revokeToken = useCallback(
    async (tokenId: string) => {
      if (!isCurrent()) return;
      await revokeTokenMutate(`/health-metrics/tokens/${tokenId}`);
      if (!isCurrent()) return;
      setTokens(undefined);
      await refetchTokens();
    },
    [revokeTokenMutate, refetchTokens, isCurrent, setTokens]
  );

  const deleteKind = useCallback(
    async (kind: HealthMetricsKind) => {
      if (!isCurrent()) return;
      const result = await deleteKindMutate(`/health-metrics?kind=${kind}`);
      if (!isCurrent()) return;
      if (result) setAggregate(undefined);
      await refetchAggregate();
      return result;
    },
    [deleteKindMutate, refetchAggregate, isCurrent, setAggregate]
  );

  const deleteAll = useCallback(async () => {
    if (!isCurrent()) return;
    const result = await deleteAllMutate('/health-metrics/all');
    if (!isCurrent()) return;
    if (result) setAggregate(undefined);
    await refetchAggregate();
    return result;
  }, [deleteAllMutate, refetchAggregate, isCurrent, setAggregate]);

  const updateAgentsEnabled = useCallback(
    async (enabled: boolean) => {
      if (!isCurrent()) return;
      return updateAgentsPreferenceMutate('/auth/me/health-metrics-agents-preference', {
        health_metrics_agents_enabled: enabled,
      });
    },
    [updateAgentsPreferenceMutate, isCurrent]
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
