'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';

interface OwnedSchema<T> {
  safeParse(value: unknown): { success: true; data: T } | { success: false };
}
/** Native query/mutation boundary shared by the two account-owned world preferences. */
export function useWorldOwnerPreferences<T extends { owner_id: string }, W>(
  ownerId: string,
  enabled: boolean,
  resource: 'home' | 'avatar',
  schema: OwnedSchema<T>
) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const pending = useRef<AbortController | null>(null);
  const endpoint = '/world/' + resource;
  const query = useApiQuery<unknown>(endpoint, {
    enabled,
    deps: [ownerId],
    componentName: 'WorldPreferences',
  });
  const { refetch, acceptData } = query;
  const { mutate, loading } = useApiMutation<W, unknown>({
    method: 'PUT',
    componentName: 'WorldPreferences',
    retainResponse: false,
  });
  const result = useMemo(() => schema.safeParse(query.data), [query.data, schema]);
  const value =
    enabled && isCurrent() && result.success && result.data.owner_id === ownerId
      ? result.data
      : null;
  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [ownerId, resource, enabled]
  );
  useEffect(() => {
    if (!enabled) return;
    const refresh = () => {
      if (!document.hidden && isCurrent()) void refetch();
    };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [enabled, isCurrent, refetch]);
  async function save(payload: W): Promise<T | null> {
    if (!enabled || !isCurrent() || pending.current) return null;
    const controller = new AbortController();
    pending.current = controller;
    try {
      const response = await mutate(endpoint, payload, { signal: controller.signal });
      const parsed = schema.safeParse(response);
      if (!isCurrent() || controller.signal.aborted) return null;
      if (!parsed.success || parsed.data.owner_id !== ownerId)
        throw new Error('world_' + resource + '_unavailable');
      return acceptData(parsed.data) ? parsed.data : null;
    } finally {
      if (pending.current === controller) pending.current = null;
    }
  }
  return {
    value,
    loading: query.loading,
    failed: enabled && (!!query.error || (query.data !== undefined && !value)),
    saving: loading,
    save,
    refresh: refetch,
    reload: query.refetchVerified,
  };
}
