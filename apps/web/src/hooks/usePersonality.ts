/**
 * usePersonality Hook
 * Reads the user's conversational style from the shared personality store.
 *
 * The state deliberately does NOT live here. It used to — in `useState` — and
 * that gave every consumer a private copy, so changing the style in Settings
 * left the header showing the previous one until the page was reloaded by hand
 * (reported 2026-08-07, on production and on the public demonstrator). Three
 * components read this preference, and it is one preference.
 *
 * The public shape is unchanged: callers keep the same object.
 */

import { useCallback, useEffect } from 'react';

import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';

import { useAuth } from '@/hooks/useAuth';
import { usePersonalityStore } from '@/stores/personalityStore';
import { PersonalityListItem } from '@/types/personality';

export interface UsePersonalityReturn {
  /** List of available personalities */
  personalities: PersonalityListItem[];
  /** User's current personality (null = default) */
  currentPersonality: PersonalityListItem | null;
  /** Current personality ID */
  currentPersonalityId: string | null;
  /** First load only — the moment where there is nothing to show yet. */
  loading: boolean;
  /**
   * A reload of content already on screen. Set `aria-busy` from it; never
   * swap the content out.
   *
   * Both consumers replace their whole subtree while `loading` — the header
   * selector with a disabled placeholder, the settings panel with a spinner.
   * Since this state is shared, an administrator saving a style in Settings
   * would otherwise blank the header of the entire application (apps/web
   * CLAUDE.md: "a refresh is not a first load").
   */
  refreshing: boolean;
  /** Loading state for update operation */
  updating: boolean;
  /** Error state */
  error: Error | null;
  /** Update personality preference */
  updatePersonality: (personalityId: string | null) => Promise<void>;
  /** Refetch personalities and current preference */
  refetch: () => Promise<void>;
}

export function usePersonality(): UsePersonalityReturn {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const ownerId = usePersonalityStore(state => state.ownerId);

  // Field-by-field selectors: subscribing to the whole store would re-render
  // every consumer on any change, including the `updating` flag of a sibling.
  const personalities = usePersonalityStore(state => state.personalities);
  const currentPersonality = usePersonalityStore(state => state.currentPersonality);
  const currentPersonalityId = usePersonalityStore(state => state.currentPersonalityId);
  const storeLoading = usePersonalityStore(state => state.loading);
  const hasLoaded = usePersonalityStore(state => state.hasLoaded);
  const updating = usePersonalityStore(state => state.updating);
  const error = usePersonalityStore(state => state.error);
  const load = usePersonalityStore(state => state.load);
  const refetch = usePersonalityStore(state => state.refetch);
  const updatePersonality = usePersonalityStore(state => state.updatePersonality);

  useEffect(() => {
    let cancelled = false;
    // Strict Mode's probe is cleaned up before external IO; consumers still
    // share the store's one load for their account.
    queueMicrotask(() => {
      if (!cancelled) void load(userId);
    });
    return () => {
      cancelled = true;
    };
  }, [load, userId]);

  const updateForOwner = useCallback(
    async (personalityId: string | null) => {
      if (!isCurrent() || usePersonalityStore.getState().ownerId !== userId) return;
      await updatePersonality(personalityId);
    },
    [isCurrent, userId, updatePersonality]
  );

  const refetchForOwner = useCallback(async () => {
    if (!isCurrent() || usePersonalityStore.getState().ownerId !== userId) return;
    await refetch();
  }, [isCurrent, userId, refetch]);

  const ownsState = userId !== null && ownerId === userId;

  return {
    personalities: ownsState ? personalities : [],
    currentPersonality: ownsState ? currentPersonality : null,
    currentPersonalityId: ownsState ? currentPersonalityId : null,
    // Before the first attempt settles there is no data to show, and a
    // consumer that renders an empty list at that instant flashes "no style"
    // where the previous hook showed its spinner from the first paint.
    // Monotone on purpose: once something is on screen, it stays.
    loading: userId !== null && (!ownsState || !hasLoaded),
    refreshing: ownsState && storeLoading && hasLoaded,
    updating: ownsState && updating,
    error: ownsState ? error : null,
    updatePersonality: updateForOwner,
    refetch: refetchForOwner,
  };
}
