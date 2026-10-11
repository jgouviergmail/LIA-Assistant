'use client';

/**
 * useChatShortcuts — user-defined slash shortcuts (SLASH admin lot;
 * server-persisted in users.chat_shortcuts).
 *
 * Same contract as useBriefingPreferences: GET returns the sanitized list
 * (plus the runtime count cap), `save` is a full replace with optimistic
 * local state and rollback on error.
 */

import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationPreferenceState } from '@/hooks/useApplicationPreferenceState';
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
  const { data, loading, error, refetch, ownerId } = useApplicationAccountQuery<ChatShortcutsResponse>(ENDPOINT, 'useChatShortcuts', enabled);
  const { mutate, loading: saving } = useApiMutation<ChatShortcutsPayload, ChatShortcutsResponse>({
    method: 'PUT',
    componentName: 'useChatShortcuts',
  });
  const write = useCallback((next: UserChatShortcut[]) => mutate(ENDPOINT, { shortcuts: next }), [mutate]);
  const saved = useMemo(() => data?.shortcuts ?? [], [data?.shortcuts]);
  const { value, save } = useApplicationPreferenceState(ownerId, saved, 'chat_shortcuts', refetch, write);

  return {
    shortcuts: value ?? [],
    maxCount: data?.max_count ?? 0,
    loading,
    error: !!error,
    save,
    saving,
  };
}
