/**
 * API hook for the Psyche Engine.
 *
 * Follows the useJournals pattern: useApiQuery for GET, useApiMutation for POST/PATCH.
 * Syncs full state into Zustand store on initial load.
 *
 * Phase: evolution — Psyche Engine (Iteration 1)
 * Created: 2026-04-01
 */

import { useCallback, useEffect, useRef } from 'react';

import { useApplicationAccountState } from './useApplicationAccountState';
import type { ApplicationAccountLifetime } from './useApplicationAccountLifetime';

import { useApiMutation } from './useApiMutation';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';

import { usePsycheStore } from '@/stores/psycheStore';
import { usePersonalityStore } from '@/stores/personalityStore';
import type { PsycheSettings, PsycheSettingsUpdate, PsycheState } from '@/types/psyche';

interface PsycheResetResponse {
  status: string;
  level: string;
}

const releasePsycheOverride = () => {};

function syncPsycheSettings(settings: PsycheSettings) {
  const store = usePsycheStore.getState();
  store.setDisplayAvatar(settings.psyche_display_avatar);
  store.setEnabled(settings.psyche_enabled);
}

export function usePsyche() {
  // Both style selectors share this confirmed server preference. Its stable
  // identity rereads OCEAN without reacting to pending saves or catalogue copy.
  const personalityKey = usePersonalityStore(
    state =>
      `${state.ownerId ?? ''}:${state.currentPersonality?.id ?? state.currentPersonalityId ?? ''}`
  );
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
    acceptState,
    { deps: [personalityKey] }
  );
  const {
    data: stateData,
    loading: stateLoading,
    error: stateError,
    acceptData: acceptStateData,
    refetch: refetchState,
    ownerId,
    lifetime,
    isCurrent,
  } = stateQuery;

  // GET /psyche/settings
  const {
    data: settingsData,
    loading: settingsLoading,
    error: settingsError,
    acceptData: acceptSettings,
    refetch: refetchSettings,
  } = useApplicationAccountQuery<PsycheSettings>(
    '/psyche/settings',
    'usePsyche',
    true,
    syncPsycheSettings
  );

  const refetchPsyche = useCallback(async () => {
    await Promise.all([refetchState(), refetchSettings()]);
  }, [refetchState, refetchSettings]);
  useApplicationResourceSync(ownerId, 'psyche', refetchPsyche, releasePsycheOverride);

  useEffect(() => {
    usePsycheStore.getState().bindOwner(ownerId ?? null);
  }, [ownerId]);

  // PATCH /psyche/settings
  const { mutate: updateSettingsMutate } = useApiMutation<PsycheSettingsUpdate, PsycheSettings>({
    method: 'PATCH',
    componentName: 'usePsyche',
  });

  // POST /psyche/reset
  const { mutate: resetMutate } = useApiMutation<{ level: string }, PsycheResetResponse>({
    method: 'POST',
    componentName: 'usePsyche',
  });

  const activeMutation = useRef<ApplicationAccountLifetime | null>(null);
  const [pendingMutation, setPendingMutation] = useApplicationAccountState<
    'settings' | 'reset' | null
  >(ownerId, null);

  const beginMutation = useCallback(
    (operation: 'settings' | 'reset') => {
      if (!isCurrent() || activeMutation.current === lifetime) return false;
      activeMutation.current = lifetime;
      setPendingMutation(operation);
      return true;
    },
    [isCurrent, lifetime, setPendingMutation]
  );

  const finishMutation = useCallback(() => {
    if (activeMutation.current !== lifetime) return;
    activeMutation.current = null;
    setPendingMutation(null);
  }, [lifetime, setPendingMutation]);

  const updateSettings = useCallback(
    async (data: PsycheSettingsUpdate) => {
      if (!beginMutation('settings')) return null;
      try {
        const result = await updateSettingsMutate('/psyche/settings', data);
        if (!isCurrent()) return null;
        if (result) {
          acceptSettings(result);
          // The PATCH is confirmed even if this independent read fails. The
          // query retains that confirmed value and exposes its read error.
          await refetchSettings().catch(() => {});
        }
        return isCurrent() ? result : null;
      } catch (error) {
        if (!isCurrent()) return null;
        throw error;
      } finally {
        finishMutation();
      }
    },
    [
      beginMutation,
      updateSettingsMutate,
      acceptSettings,
      refetchSettings,
      isCurrent,
      finishMutation,
    ]
  );

  const resetPsyche = useCallback(
    async (level: 'soft' | 'full' | 'purge') => {
      if (!beginMutation('reset')) return null;
      try {
        const result = await resetMutate('/psyche/reset', { level });
        if (!isCurrent()) return null;
        if (result) {
          // The old snapshot no longer describes the confirmed reset. Keep
          // it cleared if the observational read cannot return the new one.
          acceptStateData(null);
          await refetchState().catch(() => {});
        }
        return isCurrent() ? result : null;
      } catch (error) {
        if (!isCurrent()) return null;
        throw error;
      } finally {
        finishMutation();
      }
    },
    [beginMutation, resetMutate, acceptStateData, refetchState, isCurrent, finishMutation]
  );

  return {
    state: stateData,
    settings: settingsData,
    error: stateError ?? settingsError,
    stateError,
    settingsError,
    isLoading:
      (stateLoading && stateData === undefined) || (settingsLoading && settingsData === undefined),
    isRefreshing:
      (stateLoading && stateData !== undefined) || (settingsLoading && settingsData !== undefined),
    isUpdatingSettings: pendingMutation === 'settings',
    isResetting: pendingMutation === 'reset',
    updateSettings,
    resetPsyche,
    refetchState,
    refetchSettings,
  };
}
