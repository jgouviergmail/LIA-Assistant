'use client';

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react';
import { useTheme } from 'next-themes';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useAuth } from '@/hooks/useAuth';
import { useHydrated } from '@/hooks/useHydrated';
import {
  type DisplayMode,
  type ThemeModeState,
  type TransitionOrigin,
  applyOledAttribute,
  fromPersistedTheme,
  readStoredOled,
  toPersistedTheme,
  withThemeTransition,
  writeStoredOled,
} from '@/lib/theme-mode';
import type { User } from '@/lib/auth';

export interface UseThemeMode {
  /** False until the client has read the stored flag — render no state-dependent UI before it. */
  mounted: boolean;
  /** The chosen mode, `system` included. */
  mode: DisplayMode;
  /** What `system` actually resolves to right now. */
  resolved: 'light' | 'dark';
  /** OLED refinement, only meaningful while `resolved` is dark. */
  oled: boolean;
  /**
   * Apply a state: DOM, storage, and the user record if signed in.
   *
   * `origin` is the point the circular reveal opens from — the centre of the
   * control that was pressed. Omitted, the change is instant.
   */
  apply: (next: ThemeModeState, origin?: TransitionOrigin) => Promise<void>;
}

/**
 * Single owner of the display-mode state.
 *
 * Both the header's circular toggle and the Settings panel drive the same three
 * things — `next-themes`, the `data-oled` attribute, and `users.theme` — and
 * having each own its copy is how the two would drift: one persisting `'oled'`,
 * the other forgetting the attribute, with only one of them clearing storage.
 *
 * The mount effect adopts whatever the blocking script already applied, so the
 * hook never contradicts the paint that already happened.
 */
function subscribeOled(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-oled'] });
  return () => observer.disconnect();
}
const readOled = () => document.documentElement.hasAttribute('data-oled');
const serverOled = () => false;

export function useThemeMode(): UseThemeMode {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const oled = useSyncExternalStore(subscribeOled, readOled, serverOled);
  const mounted = useHydrated();
  const { user, refreshUser } = useAuth();
  const userId = user?.id;
  const lastAccountTheme = useRef<{ id: string; theme: string } | null>(null);

  const { mutate: updateTheme } = useApiMutation<{ theme: string }, User>({
    method: 'PATCH',
    componentName: 'useThemeMode',
    onSuccess: async () => {
      await refreshUser?.();
    },
  });

  useEffect(() => {
    applyOledAttribute(readStoredOled());
  }, []);

  useEffect(() => {
    if (!user?.theme) return;
    const hadAccountValue = lastAccountTheme.current?.id === user.id;
    const changedAccount = lastAccountTheme.current !== null && !hadAccountValue;
    lastAccountTheme.current = { id: user.id, theme: user.theme };
    const stored = fromPersistedTheme(user.theme);
    // Compared against the CHOSEN mode, never the resolved one. A record saying
    // "dark" for a user sitting on `system` that happens to resolve dark looks
    // identical on screen but is a different setting — leaving it unapplied
    // makes Settings show "System" while the server says "Dark".
    if ((stored.mode !== 'system' || hadAccountValue || changedAccount) && stored.mode !== theme)
      setTheme(stored.mode);
    if (stored.oled !== readStoredOled()) {
      writeStoredOled(stored.oled);
      applyOledAttribute(stored.oled);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.theme]);

  // Latest value the user has asked for, and whether a write loop is draining.
  // Refs, not state: they must be readable and writable synchronously from
  // inside a single event, before React has re-rendered anything.
  const desiredRef = useRef<{ userId: string; value: string } | null>(null);
  const writingRef = useRef(false);

  /**
   * Persist, serialised and coalesced.
   *
   * `useApiMutation` offers no ordering guarantee and neither does HTTP, so
   * three quick presses used to race three PATCHes to the same row — the server
   * could settle on a state the user had already left. One write is in flight
   * at a time, and anything chosen meanwhile simply overwrites the pending
   * value: the user's intermediate steps are not worth a round-trip, only where
   * they came to rest.
   */
  const persist = useCallback(
    async (userId: string, value: string) => {
      desiredRef.current = { userId, value };
      if (writingRef.current) return;

      writingRef.current = true;
      try {
        while (desiredRef.current !== null) {
          const pending = desiredRef.current;
          desiredRef.current = null;
          try {
            await updateTheme(`/users/${pending.userId}`, { theme: pending.value });
          } catch {
            // Keep the local choice; the mutation reports the failed request.
            // A queued newer choice still gets its own single attempt.
          }
        }
      } finally {
        writingRef.current = false;
      }
    },
    [updateTheme]
  );

  const apply = useCallback(
    async (next: ThemeModeState, origin?: TransitionOrigin) => {
      // Both DOM mutations happen inside ONE view transition, synchronously:
      // the API snapshots before and after the callback, so splitting them
      // would capture a half-applied theme in the "after" frame.
      withThemeTransition(() => {
        // OLED before the theme: `disableTransitionOnChange` only wraps
        // `setTheme`, so the attribute carries its own suppression. Doing both
        // before the next paint stops the two halves of an OLED → light press
        // from animating against each other.
        if (next.oled !== oled) {
          writeStoredOled(next.oled);
          applyOledAttribute(next.oled);
        }
        setTheme(next.mode);
      }, origin);

      if (userId) {
        await persist(userId, toPersistedTheme(next));
      }
    },
    [oled, setTheme, userId, persist]
  );

  return {
    mounted,
    mode: (theme as DisplayMode) ?? 'system',
    resolved: resolvedTheme === 'dark' ? 'dark' : 'light',
    oled,
    apply,
  };
}
