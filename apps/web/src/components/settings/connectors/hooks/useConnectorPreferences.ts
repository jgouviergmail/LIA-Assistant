/**
 * Hook for connector preferences management.
 * Handles loading, saving, and clearing connector-specific preferences.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { CONNECTORS_WITH_PREFERENCES, PREFERENCE_FIELDS } from '../constants';
import type { Connector, ConnectorPreferences } from '../types';

interface UseConnectorPreferencesOptions {
  connectors: Connector[];
  t: (key: string) => string;
}

interface UseConnectorPreferencesReturn {
  savedPrefs: Record<string, ConnectorPreferences>;
  savingPreference: string | null;
  selectPreference: (connectorId: string, connectorType: string, value: string) => Promise<void>;
}

export function useConnectorPreferences({
  connectors,
  t,
}: UseConnectorPreferencesOptions): UseConnectorPreferencesReturn {
  const [savedPrefs, setSavedPrefs] = useState<Record<string, ConnectorPreferences>>({});
  const [savingPreference, setSavingPreference] = useState<string | null>(null);
  const [preferencesLoaded, setPreferencesLoaded] = useState<Record<string, boolean>>({});
  // Connectors whose GET is in flight. `preferencesLoaded` can only be raised
  // once the response is in, so it does not cover the window in between: a
  // parent re-render carrying a new `connectors` array (the optimistic
  // add/remove in UserConnectorsSection produces one) would re-enter and fire a
  // second request for the same connector.
  const loadingRef = useRef<Set<string>>(new Set());
  // Connectors the user has edited during this session. A load response must
  // never overwrite a local write that landed while it was in flight.
  const locallyEditedRef = useRef<Set<string>>(new Set());

  // Load preferences for connectors that support them
  useEffect(() => {
    const loadPreferences = async (connector: Connector) => {
      if (!CONNECTORS_WITH_PREFERENCES.includes(connector.connector_type)) return;
      if (preferencesLoaded[connector.id] || loadingRef.current.has(connector.id)) return;
      loadingRef.current.add(connector.id);

      try {
        const response = await apiClient.get<{ preferences: ConnectorPreferences }>(
          `/connectors/${connector.id}/preferences`
        );
        const prefs = response.preferences || {};
        setSavedPrefs(prev =>
          locallyEditedRef.current.has(connector.id)
            ? prev
            : { ...prev, [connector.id]: { ...prefs } }
        );
      } catch {
        // Silently fail - preferences are optional
        logger.debug(`No preferences found for connector ${connector.id}`);
      } finally {
        loadingRef.current.delete(connector.id);
        setPreferencesLoaded(prev => ({ ...prev, [connector.id]: true }));
      }
    };

    connectors.forEach(connector => {
      loadPreferences(connector);
    });
  }, [connectors, preferencesLoaded]);

  // Select a preference value (save or clear) with optimistic update
  const selectPreference = useCallback(
    async (connectorId: string, connectorType: string, value: string) => {
      const prefField = PREFERENCE_FIELDS[connectorType];
      if (!prefField) return;

      setSavingPreference(connectorId);
      // Claim the local value: a preference GET still in flight must not
      // overwrite what the user just chose (released again on rollback).
      locallyEditedRef.current.add(connectorId);

      // Optimistic update: save previous state for rollback
      const previousPrefs = { ...savedPrefs[connectorId] };
      setSavedPrefs(prev => ({
        ...prev,
        [connectorId]: { ...prev[connectorId], [prefField]: value },
      }));

      try {
        await apiClient.patch(`/connectors/${connectorId}/preferences`, {
          [prefField]: value,
        });
        toast.success(
          value
            ? t('settings.connectors.preferences.saved')
            : t('settings.connectors.preferences.cleared')
        );
      } catch (error: unknown) {
        // Rollback on failure. Releasing the claim first matters: the local
        // value is back to what it was before the edit, so a load that is still
        // in flight is welcome to fill it in rather than leaving a hole.
        locallyEditedRef.current.delete(connectorId);
        setSavedPrefs(prev => ({
          ...prev,
          [connectorId]: previousPrefs,
        }));

        const apiError = error as {
          response?: { data?: { detail?: { errors?: string[] } | string } };
        };
        logger.error('Failed to save connector preference', error as Error, {
          component: 'useConnectorPreferences',
          connectorId,
          connectorType,
        });
        toast.error(
          apiError.response?.data?.detail && typeof apiError.response.data.detail === 'object'
            ? apiError.response.data.detail.errors?.join(', ')
            : t('settings.connectors.preferences.error')
        );
      } finally {
        setSavingPreference(null);
      }
    },
    [savedPrefs, t]
  );

  return {
    savedPrefs,
    savingPreference,
    selectPreference,
  };
}
