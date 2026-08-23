'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTheme } from 'next-themes';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useAuth } from '@/hooks/useAuth';
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
export function useThemeMode(): UseThemeMode {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [oled, setOled] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { user, refreshUser } = useAuth();

  const { mutate: updateTheme } = useApiMutation<{ theme: string }, User>({
    method: 'PATCH',
    componentName: 'useThemeMode',
    onSuccess: async () => {
      await refreshUser?.();
    },
  });

  useEffect(() => {
    setOled(readStoredOled());
    setMounted(true);
  }, []);

  // One-way sync, server → local. Keyed on the persisted value ALONE: adding
  // the local state to the deps would re-run this after every toggle and undo
  // the user's own click before they saw it.
  useEffect(() => {
    if (!user?.theme) return;
    const stored = fromPersistedTheme(user.theme);
    // Compared against the CHOSEN mode, never the resolved one. A record saying
    // "dark" for a user sitting on `system` that happens to resolve dark looks
    // identical on screen but is a different setting — leaving it unapplied
    // makes Settings show "System" while the server says "Dark".
    if (stored.mode !== 'system' && stored.mode !== theme) setTheme(stored.mode);
    if (stored.oled !== readStoredOled()) {
      setOled(stored.oled);
      writeStoredOled(stored.oled);
      applyOledAttribute(stored.oled);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.theme]);

  // Latest value the user has asked for, and whether a write loop is draining.
  // Refs, not state: they must be readable and writable synchronously from
  // inside a single event, before React has re-rendered anything.
  const desiredRef = useRef<string | null>(null);
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
      desiredRef.current = value;
      if (writingRef.current) return;

      writingRef.current = true;
      try {
        while (desiredRef.current !== null) {
          const pending = desiredRef.current;
          desiredRef.current = null;
          await updateTheme(`/users/${userId}`, { theme: pending });
        }
      } catch {
        // A theme preference is best-effort. `useApiMutation` has already
        // logged the failure with its status and payload; rethrowing here would
        // only surface as an unhandled rejection from an onClick handler, and
        // would cost the user nothing but the local change they can see worked.
        desiredRef.current = null;
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
          setOled(next.oled);
          writeStoredOled(next.oled);
          applyOledAttribute(next.oled);
        }
        setTheme(next.mode);
      }, origin);

      if (user?.id) {
        await persist(user.id, toPersistedTheme(next));
      }
    },
    [oled, setTheme, user?.id, persist]
  );

  return {
    mounted,
    mode: (theme as DisplayMode) ?? 'system',
    resolved: resolvedTheme === 'dark' ? 'dark' : 'light',
    oled,
    apply,
  };
}
