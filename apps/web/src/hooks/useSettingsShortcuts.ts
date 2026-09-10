'use client';

/**
 * useSettingsShortcuts — the settings sections a person pinned to the
 * floating dock (ADR-277; server-persisted in users.settings_shortcuts).
 *
 * Same contract as useChatShortcuts: GET returns the sanitized list plus the
 * runtime cap, `save` is a full replace with optimistic local state and a
 * rollback on error — and, on success, a refresh of the signed-in user, since
 * the dock on every screen reads the list from `useAuth()` rather than
 * fetching it itself.
 *
 * The backend keeps only the tokens' SHAPE (a slug); their meaning is
 * `SETTINGS_SECTIONS`. A token the page no longer declares — a section
 * renamed or removed since it was pinned — is dropped at read time, never
 * shown as a dead link. The picker's own section is dropped too: a shortcut
 * to the place where shortcuts are chosen is the one that helps nobody.
 */

import { useCallback, useMemo, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAuth } from '@/hooks/useAuth';
import { isSettingsSectionToken, type SettingsSectionToken } from '@/lib/settings-sections';

const ENDPOINT = '/users/me/settings-shortcuts';

/** The picker's own token — never offered, never shown in the dock. */
export const MY_SHORTCUTS_TOKEN = 'my-shortcuts' satisfies SettingsSectionToken;

interface SettingsShortcutsResponse {
  shortcuts: string[];
  max_count: number;
}

interface SettingsShortcutsPayload {
  shortcuts: string[];
}

/**
 * The stored tokens this build of the page still knows, in stored order.
 *
 * Args:
 *   raw: The list as the API published it (or as `useAuth().user` carries it).
 *
 * Returns:
 *   Known tokens only, the picker's own excluded, each once.
 */
export function knownShortcutTokens(
  raw: readonly string[] | null | undefined
): SettingsSectionToken[] {
  const seen = new Set<SettingsSectionToken>();
  for (const token of raw ?? []) {
    if (isSettingsSectionToken(token) && token !== MY_SHORTCUTS_TOKEN) seen.add(token);
  }
  return [...seen];
}

export interface UseSettingsShortcutsReturn {
  shortcuts: SettingsSectionToken[];
  /** Runtime per-user cap, for the « N of MAX » counter (0 while loading). */
  maxCount: number;
  loading: boolean;
  error: boolean;
  /** Optimistic full replace; rolls back local state on API error. */
  save: (next: SettingsSectionToken[]) => Promise<boolean>;
  saving: boolean;
}

export function useSettingsShortcuts(enabled = true): UseSettingsShortcutsReturn {
  const { refreshUser } = useAuth();
  const { data, loading, error } = useApiQuery<SettingsShortcutsResponse>(ENDPOINT, {
    componentName: 'useSettingsShortcuts',
    enabled,
  });
  // Derived-with-override (no state-sync effect — react-hooks ratchet).
  const [override, setOverride] = useState<SettingsSectionToken[] | null>(null);
  const serverShortcuts = data?.shortcuts;
  const shortcuts = useMemo(
    () => override ?? knownShortcutTokens(serverShortcuts),
    [override, serverShortcuts]
  );

  const mutation = useApiMutation<SettingsShortcutsPayload, SettingsShortcutsResponse>({
    method: 'PUT',
    componentName: 'useSettingsShortcuts',
  });

  const save = useCallback(
    async (next: SettingsSectionToken[]): Promise<boolean> => {
      const previous = shortcuts;
      setOverride(next);
      try {
        await mutation.mutate(ENDPOINT, { shortcuts: next });
      } catch {
        setOverride(previous);
        return false;
      }
      // The dock reads `useAuth().user`: refresh it so every screen follows.
      await refreshUser();
      return true;
    },
    [shortcuts, mutation, refreshUser]
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
