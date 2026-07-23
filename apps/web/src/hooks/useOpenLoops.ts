'use client';

/**
 * useOpenLoops — the commitments ledger surface (UXR Lot 7, B5; ADR-139).
 *
 * Lists the user's OPEN loops and closes them one-tap. The router is mounted
 * only when OPEN_LOOPS_ENABLED — a 404/failure marks the surface
 * `unavailable` (the section renders nothing; belt-and-braces beside the
 * /config flag gate). Closing is optimistic with restore-on-error. No manual
 * creation: the ledger's value is being automatic (extraction-fed).
 */

import { useCallback, useState } from 'react';

import { ApiError } from '@/lib/api-client';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';

export interface OpenLoop {
  id: string;
  subject: string;
  counterparty: string | null;
  direction: 'user_owes' | 'waiting_on_other';
  /** ISO UTC advisory deadline, or null. */
  due_hint: string | null;
  created_at: string;
}

export type CloseLoopAction = 'done' | 'dismissed';

/** Direction groups, preserving the server order (due first, then age). */
export function groupLoops(loops: OpenLoop[]): {
  owed: OpenLoop[];
  waiting: OpenLoop[];
} {
  return {
    owed: loops.filter(l => l.direction === 'user_owes'),
    waiting: loops.filter(l => l.direction === 'waiting_on_other'),
  };
}

/** Whole days since creation (badge). */
export function daysOpen(createdAtIso: string, now: Date): number {
  const ms = now.getTime() - new Date(createdAtIso).getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

export interface UseOpenLoopsReturn {
  loops: OpenLoop[];
  loading: boolean;
  /** Surface absent on this instance (router unmounted, 404) — render nothing. */
  unavailable: boolean;
  /** Transient listing failure (network, 5xx) — offer a retry, not silence. */
  loadError: boolean;
  refetch: () => void;
  close: (id: string, action: CloseLoopAction) => Promise<boolean>;
}

export function useOpenLoops(enabled = true): UseOpenLoopsReturn {
  const { data, loading, error, refetch } = useApiQuery<{ items: OpenLoop[]; total: number }>(
    '/open-loops?status=open',
    { componentName: 'useOpenLoops', enabled }
  );
  // Optimistic removals (closed ids) — derived-with-override, no sync effect.
  const [removedIds, setRemovedIds] = useState<ReadonlySet<string>>(new Set());
  const loops = (data?.items ?? []).filter(l => !removedIds.has(l.id));

  const { mutate } = useApiMutation<{ action: CloseLoopAction }, OpenLoop>({
    method: 'POST',
    componentName: 'useOpenLoops',
  });

  const close = useCallback(
    async (id: string, action: CloseLoopAction): Promise<boolean> => {
      setRemovedIds(prev => new Set([...prev, id]));
      try {
        await mutate(`/open-loops/${id}/close`, { action });
        return true;
      } catch {
        setRemovedIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        return false;
      }
    },
    [mutate]
  );

  // 404 = the router is not mounted on this instance (flag off) → the
  // surface genuinely does not exist. Anything else (network, 5xx) is
  // TRANSIENT — hiding the section on a blip would silently lose the
  // feature until the next full reload (review finding).
  const notFound = error instanceof ApiError && error.status === 404;
  return {
    loops,
    loading,
    unavailable: notFound,
    loadError: !!error && !notFound,
    refetch,
    close,
  };
}
