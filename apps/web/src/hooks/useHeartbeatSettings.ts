import { useCallback, useRef, useState } from 'react';
import { useApiMutation } from './useApiMutation';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';
import { useApplicationResourceSync } from './useApplicationResourceSync';
import { publishApplicationResources } from '@/lib/application-resources';

/**
 * Heartbeat settings response from API.
 */
export interface HeartbeatSettings {
  heartbeat_enabled: boolean;
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
  /**
   * Kinds of anticipated moment the reader refuses (ADR-281).
   *
   * Optional throughout, so a response predating the feature renders exactly
   * as before rather than as "everything refused".
   */
  moment_kinds_disabled?: string[];
  /** Every kind, in display order — published, never re-declared here. */
  all_moment_kinds?: string[];
  /**
   * Kinds that would yield nothing on this account, and what each waits for.
   *
   * Already NARROWED to what is missing: for a kind, "missing" means an absent
   * connector, which only the server can know.
   */
  moment_kind_dependencies?: Record<string, string[]>;
}

/**
 * Heartbeat settings update payload (partial update).
 */
export interface HeartbeatSettingsUpdate {
  heartbeat_enabled?: boolean;
  heartbeat_notify_start_hour?: number;
  heartbeat_notify_end_hour?: number;
  /** FULL replacement of the refusal set — never a partial diff. */
  heartbeat_disabled_sources?: string[];
  /** FULL replacement of the refused moment kinds — never a partial diff. */
  moment_kinds_disabled?: string[];
}

/**
 * Hook for managing heartbeat notification settings.
 */
export function useHeartbeatSettings() {
  const { data, loading, error, refetch, ownerId } = useApplicationAccountQuery<HeartbeatSettings>(
    '/heartbeat/settings',
    'useHeartbeatSettings'
  );
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [override, setOverride] = useState<{
    lifetime: typeof lifetime;
    value: HeartbeatSettings;
  } | null>(null);
  const queues = useRef(new Map<typeof lifetime, Promise<HeartbeatSettings | undefined>>());
  const revisions = useRef(new Map<typeof lifetime, number>());
  const settings = override?.lifetime === lifetime ? override.value : data;
  const release = useCallback(() => {
    setOverride(current => (current && queues.current.has(current.lifetime) ? current : null));
  }, []);
  useApplicationResourceSync(ownerId, 'heartbeat', refetch, release);
  const { mutate: updateMutate, loading: updating } = useApiMutation<
    HeartbeatSettingsUpdate,
    HeartbeatSettings
  >({
    method: 'PATCH',
    componentName: 'useHeartbeatSettings',
  });

  const updateSettings = useCallback(
    async (data: HeartbeatSettingsUpdate): Promise<HeartbeatSettings | undefined> => {
      if (!ownerId || !isCurrent()) return undefined;
      const revision = (revisions.current.get(lifetime) ?? 0) + 1;
      revisions.current.set(lifetime, revision);
      setOverride(current => {
        const prev = current?.lifetime === lifetime ? current.value : settings;
        if (!prev) return current;
        return {
          lifetime,
          value: {
            ...prev,
            ...data,
            disabled_sources: data.heartbeat_disabled_sources ?? prev.disabled_sources,
          },
        };
      });
      const queued = queues.current.get(lifetime) ?? Promise.resolve(undefined);
      const writing = queued.then(async () => {
        if (!isCurrent()) return undefined;
        try {
          const result = await updateMutate('/heartbeat/settings', data);
          if (!result || !isCurrent()) return undefined;
          if (revisions.current.get(lifetime) === revision)
            setOverride({ lifetime, value: result });
          return result;
        } catch {
          if (isCurrent() && revisions.current.get(lifetime) === revision) {
            setOverride(current => (current?.lifetime === lifetime ? null : current));
          }
          return undefined;
        }
      });
      queues.current.set(lifetime, writing);
      try {
        return await writing;
      } finally {
        if (queues.current.get(lifetime) === writing) {
          queues.current.delete(lifetime);
          revisions.current.delete(lifetime);
          publishApplicationResources(ownerId, new Set(['heartbeat']));
        }
      }
    },
    [ownerId, isCurrent, lifetime, settings, updateMutate]
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
