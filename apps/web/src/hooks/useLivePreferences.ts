'use client';

/**
 * The person's live conversation reflexes (ADR-299, spec A10 bis): read once,
 * replaced whole on every change (the `settings_shortcuts` doctrine — one
 * full-replace PUT, never a partial patch), and shown optimistically so a
 * switch answers at once and settles back on a refusal.
 */
import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type { LivePreferences } from '@/lib/live/types';

export const LIVE_PREFERENCES_PATH = '/live/preferences';

export interface UseLivePreferencesReturn {
  preferences: LivePreferences | null;
  loading: boolean;
  saving: boolean;
  loadError: boolean;
  /** Merge, PUT the whole, keep the answer; resolves false on a refusal. */
  save: (patch: Partial<LivePreferences>) => Promise<boolean>;
  refetch: () => Promise<void>;
}

export function useLivePreferences(enabled = true): UseLivePreferencesReturn {
  const { data, loading, error, refetch, setData } = useApiQuery<LivePreferences>(
    LIVE_PREFERENCES_PATH,
    { componentName: 'useLivePreferences', enabled }
  );
  const { mutate, loading: saving } = useApiMutation<LivePreferences, LivePreferences>({
    method: 'PUT',
    componentName: 'useLivePreferences',
  });
  const [pending, setPending] = useState<LivePreferences | null>(null);

  const save = useCallback(
    async (patch: Partial<LivePreferences>): Promise<boolean> => {
      if (!data) return false;
      const next: LivePreferences = { ...data, ...patch };
      setPending(next);
      try {
        const saved = await mutate(LIVE_PREFERENCES_PATH, next);
        if (saved) setData(saved);
        return true;
      } catch {
        return false;
      } finally {
        setPending(null);
      }
    },
    [data, mutate, setData]
  );

  return {
    preferences: pending ?? data ?? null,
    loading,
    saving,
    loadError: error !== null,
    save,
    refetch,
  };
}
