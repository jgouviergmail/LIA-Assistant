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
 *
 * A pinned section the account cannot open NOW — its capability switched off
 * by the operator, a device that cannot offer it — stays in the stored list
 * and is drawn by nobody (`openableShortcutTokens`): what is pinned belongs to
 * the account, and it comes back with what closed it.
 */

import { useCallback, useMemo } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationPreferenceState } from '@/hooks/useApplicationPreferenceState';
import { useAuth } from '@/hooks/useAuth';
import {
  isSectionAvailable,
  SETTINGS_SEARCH_META,
  type SettingsSearchAvailability,
} from '@/lib/settings-search';
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

/**
 * The pinned sections this account can open now, in stored order — what the
 * dock draws and what the picker counts (ADR-277, D7).
 *
 * @param tokens - The pinned sections this build knows.
 * @param availability - The verdicts the surface holds.
 * @returns The tokens whose section those verdicts do not rule out.
 */
export function openableShortcutTokens(
  tokens: readonly SettingsSectionToken[],
  availability: SettingsSearchAvailability
): SettingsSectionToken[] {
  return tokens.filter(token => isSectionAvailable(SETTINGS_SEARCH_META[token].gate, availability));
}

/**
 * The list to save after a tick, in stored order.
 *
 * A pin the account cannot open now stays stored — it comes back to the dock
 * with what closed it — and gives its place, last first, only when the person
 * takes the last one: the picker counts what the dock draws, so a pin nobody
 * can see must never be what refuses a choice.
 *
 * @param stored - Every pinned section, as saved.
 * @param openable - Those the account can open now (`openableShortcutTokens`).
 * @param toggled - The section whose box was ticked or unticked.
 * @param maxCount - The published cap; 0 while it is not known (none applied here).
 * @returns The full list to send.
 */
export function nextShortcutTokens(
  stored: readonly SettingsSectionToken[],
  openable: readonly SettingsSectionToken[],
  toggled: SettingsSectionToken,
  maxCount: number
): SettingsSectionToken[] {
  if (stored.includes(toggled)) return stored.filter(token => token !== toggled);
  const next = [...stored, toggled];
  if (maxCount <= 0) return next;
  const drawn = new Set<SettingsSectionToken>([...openable, toggled]);
  for (let index = next.length - 1; index >= 0 && next.length > maxCount; index -= 1) {
    if (!drawn.has(next[index])) next.splice(index, 1);
  }
  return next;
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
  const { data, loading, error, refetch, ownerId } =
    useApplicationAccountQuery<SettingsShortcutsResponse>(
      ENDPOINT,
      'useSettingsShortcuts',
      enabled
    );
  const { mutate, loading: saving } = useApiMutation<
    SettingsShortcutsPayload,
    SettingsShortcutsResponse
  >({
    method: 'PUT',
    componentName: 'useSettingsShortcuts',
  });
  const write = useCallback(
    (next: SettingsSectionToken[]) => mutate(ENDPOINT, { shortcuts: next }),
    [mutate]
  );
  const saved = useMemo(() => knownShortcutTokens(data?.shortcuts), [data?.shortcuts]);
  const { value, save: saveState } = useApplicationPreferenceState(
    ownerId,
    saved,
    'profile',
    refetch,
    write
  );
  const save = useCallback(
    async (next: SettingsSectionToken[]): Promise<boolean> => {
      if (!(await saveState(next))) return false;
      await refreshUser();
      return true;
    },
    [saveState, refreshUser]
  );

  return {
    shortcuts: value ?? [],
    maxCount: data?.max_count ?? 0,
    loading,
    error: !!error,
    save,
    saving,
  };
}
