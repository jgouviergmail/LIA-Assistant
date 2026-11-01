'use client';

/**
 * One item of the « Tools » section read by its id (ADR-369): the open
 * message, event, contact or file.
 *
 * Shaped after `useWorkbenchPage`: loading is DERIVED from the key (the
 * account, the path, the params), so opening another item never shows the
 * previous one as its answer, a late answer to the previous id is dropped, and
 * a change of account clears it at once. A refresh re-reads IN PLACE — what is
 * on screen stays until its answer lands — and a failed one withdraws it
 * (owner rule 2026-10-21). `setItem` applies an optimistic or confirmed change
 * without a read.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import apiClient, { type QueryParamValue } from '@/lib/api-client';
import { paramsOf, serialiseParams } from '@/lib/workbench/params';

export interface WorkbenchItemState<T> {
  /** The item, once read for the current key. */
  item: T | undefined;
  /** The current key's item is not read yet. */
  loading: boolean;
  /** Why the last read failed (`workbenchRefusal` tells it), else null. */
  error: unknown;
  refresh: () => Promise<void>;
  /** A change to the shown item, from what is shown; nothing when nothing is. */
  setItem: (change: (current: T) => T) => void;
}

interface Read<T> {
  key: string;
  item: T | undefined;
  error: unknown;
}

/**
 * @param path - The item's endpoint; null reads nothing.
 * @param params - What names it (its id); part of the key.
 * @returns The item's state and its two gestures.
 */
export function useWorkbenchItem<T>(
  path: string | null,
  params: Readonly<Record<string, QueryParamValue>>
): WorkbenchItemState<T> {
  const { user } = useAuth();
  const owner = user?.id;
  const queryKey = serialiseParams(params);
  const key = owner && path ? `${owner}|${path}|${queryKey}` : null;
  const [read, setRead] = useState<Read<T> | null>(null);
  // Every read starts a new generation; an answer to an older one is dropped.
  const generation = useRef(0);

  useEffect(() => {
    if (key === null || path === null) return;
    const readId = ++generation.current;
    const transport = new AbortController();
    apiClient
      .get<T>(path, { params: paramsOf(queryKey), signal: transport.signal })
      .then(item => {
        if (readId === generation.current) setRead({ key, item, error: null });
      })
      .catch((error: unknown) => {
        if (readId !== generation.current || transport.signal.aborted) return;
        setRead({ key, item: undefined, error });
      });
    return () => transport.abort();
  }, [key, path, queryKey]);

  const refresh = useCallback(async () => {
    if (key === null || path === null) return;
    const readId = ++generation.current;
    try {
      const item = await apiClient.get<T>(path, { params: paramsOf(queryKey) });
      if (readId === generation.current) setRead({ key, item, error: null });
    } catch (error: unknown) {
      if (readId === generation.current) setRead({ key, item: undefined, error });
    }
  }, [key, path, queryKey]);

  const setItem = useCallback(
    (change: (current: T) => T) => {
      setRead(previous =>
        previous && previous.key === key && previous.item !== undefined
          ? { ...previous, item: change(previous.item) }
          : previous
      );
    },
    [key]
  );

  const current = read !== null && read.key === key;
  return {
    item: current ? read.item : undefined,
    loading: key !== null && !current,
    error: current ? read.error : null,
    refresh,
    setItem,
  };
}
