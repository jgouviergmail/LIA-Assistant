'use client';

/**
 * The person's live conversation reflexes (ADR-299, spec A10 bis): read once,
 * replaced whole on every change (the `settings_shortcuts` doctrine — one
 * full-replace PUT, never a partial patch), and shown optimistically so a
 * switch answers at once and settles back on a refusal.
 */
import { useCallback, useRef } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { publishApplicationResources } from '@/lib/application-resources';
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
  const { data, loading, error, refetch, setData, ownerId } =
    useApplicationAccountQuery<LivePreferences>(
      LIVE_PREFERENCES_PATH,
      'useLivePreferences',
      enabled
    );
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [pending, setPending] = useApplicationAccountState<LivePreferences | null>(ownerId, null);
  const [saving, setSaving] = useApplicationAccountState(ownerId, false);
  const queues = useRef(new Map<typeof lifetime, Promise<boolean>>());
  const desired = useRef(new Map<typeof lifetime, LivePreferences>());
  const revisions = useRef(new Map<typeof lifetime, number>());
  const release = useCallback(() => {
    if (isCurrent() && !queues.current.has(lifetime)) setPending(null);
  }, [isCurrent, lifetime, setPending]);
  useApplicationResourceSync(ownerId, 'live_preferences', refetch, release);
  const { mutate } = useApiMutation<LivePreferences, LivePreferences>({
    method: 'PUT',
    componentName: 'useLivePreferences',
  });
  const save = useCallback(
    async (patch: Partial<LivePreferences>): Promise<boolean> => {
      if (!data || !ownerId || !isCurrent()) return false;
      const next = { ...(desired.current.get(lifetime) ?? data), ...patch };
      desired.current.set(lifetime, next);
      const revision = (revisions.current.get(lifetime) ?? 0) + 1;
      revisions.current.set(lifetime, revision);
      setPending(next);
      setSaving(true);
      const queued = queues.current.get(lifetime) ?? Promise.resolve(false);
      const writing = queued.then(async () => {
        if (!isCurrent()) return false;
        try {
          const saved = await mutate(LIVE_PREFERENCES_PATH, next);
          if (!saved || !isCurrent()) return false;
          setData(saved);
          if (revisions.current.get(lifetime) === revision) setPending(saved);
          return true;
        } catch {
          return false;
        }
      });
      queues.current.set(lifetime, writing);
      try {
        const saved = await writing;
        if (!saved && isCurrent() && revisions.current.get(lifetime) === revision) setPending(null);
        return saved;
      } finally {
        if (queues.current.get(lifetime) === writing) {
          queues.current.delete(lifetime);
          desired.current.delete(lifetime);
          revisions.current.delete(lifetime);
          if (isCurrent()) {
            setSaving(false);
            publishApplicationResources(ownerId, new Set(['live_preferences']));
          }
        }
      }
    },
    [data, isCurrent, lifetime, mutate, setData, setPending, setSaving, ownerId]
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
