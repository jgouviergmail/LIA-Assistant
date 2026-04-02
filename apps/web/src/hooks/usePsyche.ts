/**
 * API hook for the Psyche Engine.
 *
 * Follows the useJournals pattern: useApiQuery for GET, useApiMutation for POST/PATCH.
 * Syncs full state into Zustand store on initial load.
 *
 * Phase: evolution — Psyche Engine (Iteration 1)
 * Created: 2026-04-01
 */

import { useCallback, useEffect } from 'react';

import { useApiMutation } from './useApiMutation';
import { useApiQuery } from './useApiQuery';

import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheSettings, PsycheSettingsUpdate, PsycheState } from '@/types/psyche';

interface PsycheResetResponse {
  status: string;
  level: string;
}

export function usePsyche() {
  // GET /psyche/state
  const {
    data: stateData,
    loading: stateLoading,
    refetch: refetchState,
  } = useApiQuery<PsycheState>('/psyche/state', {
    componentName: 'usePsyche',
  });

  // GET /psyche/settings
  const {
    data: settingsData,
    loading: settingsLoading,
    refetch: refetchSettings,
  } = useApiQuery<PsycheSettings>('/psyche/settings', {
    componentName: 'usePsyche',
  });

  // PATCH /psyche/settings
  const { mutate: updateSettingsMutate, loading: updatingSettings } = useApiMutation<
    PsycheSettingsUpdate,
    PsycheSettings
  >({
    method: 'PATCH',
    componentName: 'usePsyche',
  });

  // POST /psyche/reset
  const { mutate: resetMutate, loading: resetting } = useApiMutation<
    { level: string },
    PsycheResetResponse
  >({
    method: 'POST',
    componentName: 'usePsyche',
  });

  // Sync full state into Zustand store on initial load
  useEffect(() => {
    if (stateData) {
      usePsycheStore.getState().updateFromFullState(stateData);
    }
  }, [stateData]);

  // Sync display preference and enabled state
  useEffect(() => {
    if (settingsData) {
      usePsycheStore.getState().setDisplayAvatar(settingsData.psyche_display_avatar);
      usePsycheStore.getState().setEnabled(settingsData.psyche_enabled);
    }
  }, [settingsData]);

  // Wrapped callbacks
  const updateSettings = useCallback(
    async (data: PsycheSettingsUpdate) => {
      const result = await updateSettingsMutate('/psyche/settings', data);
      if (result) {
        await refetchSettings();
        // Sync display preference immediately
        if (data.psyche_display_avatar !== undefined) {
          usePsycheStore.getState().setDisplayAvatar(data.psyche_display_avatar);
        }
        if (data.psyche_enabled !== undefined) {
          usePsycheStore.getState().setEnabled(data.psyche_enabled);
        }
      }
      return result;
    },
    [updateSettingsMutate, refetchSettings],
  );

  const resetPsyche = useCallback(
    async (level: 'soft' | 'full' | 'purge') => {
      const result = await resetMutate('/psyche/reset', { level });
      if (result) {
        // Reset store first (immediate UX feedback), then refetch to sync server state.
        // The useEffect on stateData will update the store with fresh server data.
        usePsycheStore.getState().reset();
        await refetchState();
      }
      return result;
    },
    [resetMutate, refetchState],
  );

  return {
    state: stateData,
    settings: settingsData,
    isLoading: stateLoading || settingsLoading,
    isUpdatingSettings: updatingSettings,
    isResetting: resetting,
    updateSettings,
    resetPsyche,
    refetchState,
    refetchSettings,
  };
}
