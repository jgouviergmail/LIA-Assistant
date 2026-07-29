'use client';

/**
 * useChatShortcuts — user-defined slash shortcuts (SLASH admin lot;
 * server-persisted in users.chat_shortcuts).
 *
 * Same contract as useBriefingPreferences: GET returns the sanitized list
 * (plus the runtime count cap), `save` is a full replace with optimistic
 * local state and rollback on error.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type { UserChatShortcut } from '@/lib/slash-commands';

const ENDPOINT = '/chat/shortcuts';

interface ChatShortcutsResponse {
  shortcuts: UserChatShortcut[];
  max_count: number;
}

interface ChatShortcutsPayload {
  shortcuts: UserChatShortcut[];
}

export interface UseChatShortcutsReturn {
  shortcuts: UserChatShortcut[];
  /** Runtime per-user cap, for the "N of MAX" counter (0 while loading). */
  maxCount: number;
  loading: boolean;
  error: boolean;
  /** Optimistic full replace; rolls back local state on API error. */
  save: (next: UserChatShortcut[]) => Promise<boolean>;
  saving: boolean;
}

export function useChatShortcuts(enabled = true): UseChatShortcutsReturn {
  const { data, loading, error } = useApiQuery<ChatShortcutsResponse>(ENDPOINT, {
    componentName: 'useChatShortcuts',
    enabled,
  });
  // Derived-with-override (no state-sync effect — react-hooks ratchet).
  // Memoized so `save`'s dependency keeps a stable identity across renders.
  const [override, setOverride] = useState<UserChatShortcut[] | null>(null);
  const serverShortcuts = data?.shortcuts;
  const shortcuts = useMemo(() => override ?? serverShortcuts ?? [], [override, serverShortcuts]);

  const mutation = useApiMutation<ChatShortcutsPayload, ChatShortcutsResponse>({
    method: 'PUT',
    componentName: 'useChatShortcuts',
  });

  const save = useCallback(
    async (next: UserChatShortcut[]): Promise<boolean> => {
      const previous = shortcuts;
      setOverride(next);
      try {
        await mutation.mutate(ENDPOINT, { shortcuts: next });
        return true;
      } catch {
        setOverride(previous);
        return false;
      }
    },
    [shortcuts, mutation]
  );

  return {
    shortcuts,
    maxCount: data?.max_count ?? 0,
    loading,
    error: !!error,
    save,
    saving: mutation.loading,
  };
}
