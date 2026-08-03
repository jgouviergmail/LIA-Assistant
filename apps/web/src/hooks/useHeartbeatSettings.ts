import { useCallback } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/**
 * Heartbeat settings response from API.
 */
export interface HeartbeatSettings {
  heartbeat_enabled: boolean;
  heartbeat_min_per_day: number;
  heartbeat_max_per_day: number;
  heartbeat_push_enabled: boolean;
  heartbeat_notify_start_hour: number;
  heartbeat_notify_end_hour: number;
  /** Sources this account is CONNECTED to — a fact, not a decision. */
  available_sources: string[];
  /** Sources the reader refuses to be interrupted from (empty = none). */
  disabled_sources: string[];
  /**
   * Every toggleable source, in display order.
   *
   * Published by the server so the client never re-declares a vocabulary it
   * does not enforce — the frontend used to hard-code seven names while the
   * backend computed eight, and `health_signals` was simply never shown.
   */
  all_sources: string[];
  /**
   * Sources whose result requires another source.
   *
   * `departure` reads the calendar the first pass already fetched and returns
   * nothing without it, so refusing `calendar` leaves a live switch that
   * yields nothing forever. Published rather than guessed here: the constraint
   * lives where it is enforced (ADR-184). Optional — a response predating the
   * field simply carries no warning.
   */
  source_dependencies?: Record<string, string[]>;
}

/**
 * Heartbeat settings update payload (partial update).
 */
export interface HeartbeatSettingsUpdate {
  heartbeat_enabled?: boolean;
  heartbeat_min_per_day?: number;
  heartbeat_max_per_day?: number;
  heartbeat_push_enabled?: boolean;
  heartbeat_notify_start_hour?: number;
  heartbeat_notify_end_hour?: number;
  /** FULL replacement of the refusal set — never a partial diff. */
  heartbeat_disabled_sources?: string[];
}

/**
 * Hook for managing heartbeat notification settings.
 */
export function useHeartbeatSettings() {
  // Fetch settings
  const {
    data: settings,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<HeartbeatSettings>('/heartbeat/settings', {
    componentName: 'useHeartbeatSettings',
  });

  // Settings mutation
  const { mutate: updateMutate, loading: updating } = useApiMutation({
    method: 'PATCH',
    componentName: 'useHeartbeatSettings',
  });

  /**
   * Update heartbeat settings with optimistic update.
   */
  const updateSettings = useCallback(
    async (data: HeartbeatSettingsUpdate): Promise<HeartbeatSettings | undefined> => {
      // Optimistic update
      setData(prev => {
        if (!prev) return prev;
        return { ...prev, ...data };
      });

      const result = await updateMutate('/heartbeat/settings', data);

      if (result) {
        setData(result as HeartbeatSettings);
        return result as HeartbeatSettings;
      } else {
        // Revert on failure
        refetch();
        return undefined;
      }
    },
    [updateMutate, setData, refetch]
  );

  return {
    settings,
    loading,
    error,
    updating,
    updateSettings,
    refetch,
  };
}
