import { useCallback, useRef } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useAuth } from '@/hooks/useAuth';
import type { User } from '@/lib/auth';

/**
 * Saves the interface text size to the account: ONE request in flight, the
 * latest size wins, and the account is re-read once, after the last save.
 *
 * Holding an arrow key commits a size per step. Saved one request each, the
 * steps raced (a later PATCH could land first on another worker and leave the
 * account on an older size), and each echo re-read the account mid-flight, so
 * `FontPreferencesSync` applied an intermediate size and shrank the page back
 * under the reader. Nothing is saved for a visitor.
 *
 * @param onFailure - Called once when a save fails; the account still holds
 *   the size it had, so the caller rolls the page back and says so.
 * @returns `save(px)`, which never rejects.
 */
export function useFontSizeSave(onFailure: () => void): (px: number) => Promise<void> {
  const { user, refreshUser } = useAuth();
  const { mutate } = useApiMutation<{ font_size: number }, User>({
    method: 'PATCH',
    componentName: 'FontSizeSettings',
  });
  const queue = useRef<{ inFlight: boolean; next: number | null }>({
    inFlight: false,
    next: null,
  });
  const userId = user?.id;

  return useCallback(
    async (px: number) => {
      if (!userId) return;
      const state = queue.current;
      state.next = px;
      if (state.inFlight) return;
      state.inFlight = true;
      try {
        while (state.next !== null) {
          const target = state.next;
          state.next = null;
          await mutate(`/users/${userId}`, { font_size: target });
        }
      } catch {
        // useApiMutation already logged the failure with its status.
        state.next = null;
        onFailure();
        return;
      } finally {
        state.inFlight = false;
      }
      await refreshUser?.();
    },
    [userId, mutate, refreshUser, onFailure]
  );
}
