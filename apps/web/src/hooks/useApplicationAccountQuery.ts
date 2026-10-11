'use client';

import { useCallback, useRef, useState, type SetStateAction } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiQuery, type UseApiQueryOptions } from '@/hooks/useApiQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';

/** Account data stays hidden across owner changes until the current request returns. */
export function useApplicationAccountQuery<T>(endpoint: string, componentName: string, enabled = true, onData?: (data: T) => void, options: Pick<UseApiQueryOptions<T>, 'params' | 'deps'> = {}) {
  const { user } = useAuth();
  const ownerId = user?.id;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [accepted, setAccepted] = useState<typeof lifetime | null>(null);
  const received = useRef<typeof lifetime | null>(null);
  const onSuccess = useCallback((data: T) => {
    if (!isCurrent()) return;
    received.current = lifetime;
    setAccepted(lifetime);
    onData?.(data);
  }, [lifetime, isCurrent, onData]);
  const query = useApiQuery<T>(endpoint, {
    componentName, enabled: enabled && !!ownerId, params: options.params,
    deps: [ownerId, ...(options.deps ?? [])], onSuccess,
  });
  const { refetchVerified, setData: setQueryData } = query;
  const setData = useCallback((action: SetStateAction<T | undefined>) => {
    if (!isCurrent()) return;
    // React evaluates functional updates in order. Clear the previous account
    // before delegating its updater; no generic function cast or copy is needed.
    if (received.current !== lifetime) setQueryData(undefined);
    setQueryData(action);
    received.current = lifetime;
    setAccepted(lifetime);
  }, [isCurrent, lifetime, setQueryData]);
  const refetch = useCallback(async () => {
    if (!isCurrent()) return;
    if (ownerId && !await refetchVerified()) throw new Error('Application state refresh failed');
  }, [ownerId, refetchVerified, isCurrent]);
  const refetchCurrentVerified = useCallback(async () => {
    return isCurrent() && !!ownerId && await refetchVerified();
  }, [ownerId, refetchVerified, isCurrent]);
  return { ownerId, lifetime, isCurrent, loading: query.loading, error: query.error, refetch, setData,
    refetchVerified: refetchCurrentVerified,
    data: accepted === lifetime ? query.data : undefined };
}
