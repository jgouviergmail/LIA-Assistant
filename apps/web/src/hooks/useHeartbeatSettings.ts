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
  available_sources: string[];
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
    initialData: {
      heartbeat_enabled: false,
      heartbeat_min_per_day: 1,
      heartbeat_max_per_day: 3,
      heartbeat_push_enabled: true,
      heartbeat_notify_start_hour: 9,
      heartbeat_notify_end_hour: 22,
      available_sources: [],
    },
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
