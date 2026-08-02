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

/** Fields a user may correct on a commitment the extractor read wrong. */
export interface OpenLoopPatch {
  subject?: string;
  due_hint?: string | null;
  /** `due_hint: null` cannot mean both "unchanged" and "no deadline". */
  clear_due_hint?: boolean;
}

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
  /** Correct wording/deadline. Resolves false when the server refused. */
  update: (id: string, patch: OpenLoopPatch) => Promise<boolean>;
}

export function useOpenLoops(enabled = true): UseOpenLoopsReturn {
  const { data, loading, error, refetch } = useApiQuery<{ items: OpenLoop[]; total: number }>(
    '/open-loops?status=open',
    { componentName: 'useOpenLoops', enabled }
  );
  // Optimistic removals (closed ids) — derived-with-override, no sync effect.
  const [removedIds, setRemovedIds] = useState<ReadonlySet<string>>(new Set());
  // Same doctrine for edits: the server's row wins on the next fetch, but the
  // user sees their correction immediately instead of a value they just changed.
  const [edits, setEdits] = useState<Readonly<Record<string, OpenLoopPatch>>>({});
  const loops = (data?.items ?? [])
    .filter(l => !removedIds.has(l.id))
    .map(l => {
      const patch = edits[l.id];
      if (!patch) return l;
      return {
        ...l,
        ...(patch.subject !== undefined ? { subject: patch.subject } : {}),
        ...(patch.clear_due_hint
          ? { due_hint: null }
          : patch.due_hint !== undefined
            ? { due_hint: patch.due_hint }
            : {}),
      };
    });

  const { mutate } = useApiMutation<{ action: CloseLoopAction }, OpenLoop>({
    method: 'POST',
    componentName: 'useOpenLoops',
  });
  const { mutate: patchLoop } = useApiMutation<OpenLoopPatch, OpenLoop>({
    method: 'PATCH',
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

  const update = useCallback(
    async (id: string, patch: OpenLoopPatch): Promise<boolean> => {
      const previous = edits[id];
      setEdits(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }));
      try {
        await patchLoop(`/open-loops/${id}`, patch);
        return true;
      } catch {
        // Put the row back the way it was: showing an edit the server refused
        // is worse than showing none — the user would believe it was saved.
        setEdits(prev => {
          const next = { ...prev };
          if (previous) next[id] = previous;
          else delete next[id];
          return next;
        });
        return false;
      }
    },
    [edits, patchLoop]
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
    update,
  };
}
