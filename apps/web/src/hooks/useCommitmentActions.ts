'use client';

/**
 * useCommitmentActions — act on ONE commitment, without listing them all.
 *
 * `useOpenLoops` owns the Settings ledger: it fetches every open commitment and
 * keeps optimistic state for the list it rendered. A relation's sheet already
 * HAS its commitments (they arrive with the relation payload), so reusing that
 * hook would fetch the whole ledger a second time to act on one row.
 *
 * Callers pass `onChanged` and decide how to refresh — the sheet refetches the
 * relation, which is the only thing that also updates the counters next to it.
 */

import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import type { CloseLoopAction, OpenLoopPatch } from '@/hooks/useOpenLoops';

export interface UseCommitmentActionsReturn {
  /** Id being written right now — drives the row's busy state. */
  pendingId: string | null;
  close: (id: string, action: CloseLoopAction) => Promise<boolean>;
  update: (id: string, patch: OpenLoopPatch) => Promise<boolean>;
}

export function useCommitmentActions(onChanged: () => void): UseCommitmentActionsReturn {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const { mutate: closeLoop } = useApiMutation<{ action: CloseLoopAction }, unknown>({
    method: 'POST',
    componentName: 'useCommitmentActions',
  });
  const { mutate: patchLoop } = useApiMutation<OpenLoopPatch, unknown>({
    method: 'PATCH',
    componentName: 'useCommitmentActions',
  });

  const close = useCallback(
    async (id: string, action: CloseLoopAction) => {
      setPendingId(id);
      try {
        await closeLoop(`/open-loops/${id}/close`, { action });
        onChanged();
        return true;
      } catch {
        return false;
      } finally {
        setPendingId(null);
      }
    },
    [closeLoop, onChanged]
  );

  const update = useCallback(
    async (id: string, patch: OpenLoopPatch) => {
      setPendingId(id);
      try {
        await patchLoop(`/open-loops/${id}`, patch);
        onChanged();
        return true;
      } catch {
        return false;
      } finally {
        setPendingId(null);
      }
    },
    [patchLoop, onChanged]
  );

  return { pendingId, close, update };
}
