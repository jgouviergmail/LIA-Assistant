import { useCallback, useEffect, useRef, type Dispatch, type RefObject } from 'react';

import { fetchPendingHitl } from '@/lib/api/chat';
import { normalizeHitlPayload } from '@/lib/hitl-payload';
import { logger } from '@/lib/logger';
import type { ChatAction, ChatState } from '@/types/chat-state';

/** Reconcile the server's pending question without reviving an answered one. */
export function usePendingHitlSync(state: RefObject<ChatState>, dispatch: Dispatch<ChatAction>) {
  const active = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const cancelPendingHitlSync = useCallback(() => controller.current?.abort(), []);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      cancelPendingHitlSync();
    };
  }, [cancelPendingHitlSync]);

  const hydratePendingHitl = useCallback(async () => {
    if (!active.current) return;
    cancelPendingHitlSync();
    const request = new AbortController();
    controller.current = request;
    const expected = state.current.hitl;
    try {
      const pending = await fetchPendingHitl(request.signal);
      if (request.signal.aborted) return;
      const payload = normalizeHitlPayload(pending);
      if (pending !== null && !payload) return;
      dispatch({
        type: 'HITL_SYNC',
        payload: { payload, expected },
      });
    } catch (error) {
      if (!request.signal.aborted) {
        logger.warn('pending_hitl_sync_failed', {
          component: 'usePendingHitlSync',
          error: error instanceof Error ? error.name : 'unknown',
        });
      }
    }
  }, [cancelPendingHitlSync, dispatch, state]);

  return { hydratePendingHitl, cancelPendingHitlSync };
}
