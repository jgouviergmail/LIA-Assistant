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
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';

import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheSettings, PsycheSettingsUpdate, PsycheState } from '@/types/psyche';

interface PsycheResetResponse {
  status: string;
  level: string;
}

const releasePsycheOverride = () => {};

export function usePsyche() {
  const acceptState = useCallback((fresh: PsycheState | null) => {
    const store = usePsycheStore.getState();
    if (fresh === null) store.clearObservedState();
    else store.updateFromFullState(fresh);
  }, []);
  // GET /psyche/state
  const stateQuery = useApplicationAccountQuery<PsycheState | null>(
    '/psyche/state?initialize=false',
    'usePsyche',
    true,
    acceptState
  );
  const {
    data: stateData,
    loading: stateLoading,
    refetch: refetchState,
    ownerId,
    isCurrent,
  } = stateQuery;

  // GET /psyche/settings
  const {
    data: settingsData,
    loading: settingsLoading,
    refetch: refetchSettings,
  } = useApplicationAccountQuery<PsycheSettings>('/psyche/settings', 'usePsyche');

  const refetchPsyche = useCallback(async () => {
    await Promise.all([refetchState(), refetchSettings()]);
  }, [refetchState, refetchSettings]);
  useApplicationResourceSync(ownerId, 'psyche', refetchPsyche, releasePsycheOverride);

  useEffect(() => {
    usePsycheStore.getState().bindOwner(ownerId ?? null);
  }, [ownerId]);

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
      if (!isCurrent()) return null;
      const result = await updateSettingsMutate('/psyche/settings', data);
      if (!isCurrent()) return null;
      if (result) {
        await refetchSettings();
      }
      return isCurrent() ? result : null;
    },
    [isCurrent, updateSettingsMutate, refetchSettings]
  );

  const resetPsyche = useCallback(
    async (level: 'soft' | 'full' | 'purge') => {
      if (!isCurrent()) return null;
      const result = await resetMutate('/psyche/reset', { level });
      if (!isCurrent()) return null;
      if (result) {
        // Reset store first (immediate UX feedback), then refetch to sync server state.
        // The useEffect on stateData will update the store with fresh server data.
        usePsycheStore.getState().clearObservedState();
        await refetchState();
      }
      return isCurrent() ? result : null;
    },
    [isCurrent, resetMutate, refetchState]
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
