'use client';

/**
 * Zustand store for what this device folded on the workboard (ADR-276): the
 * lanes, and the board's figures above its filters.
 *
 * A pure display preference of the device — the `persist` pattern of the
 * shortcuts dock — deliberately outside the SEC-035 purge registry (see the
 * key's rationale in `lib/constants.ts`). WHICH categories exist is on the
 * account and never lands here: only lane keys do.
 *
 * The list is pruned on every write: a deleted category leaves a key nobody
 * will ever fold or unfold again, and a list that only grows is a leak with a
 * slow fuse.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { WORKBOARD_LANES_PREFS_KEY } from '@/lib/constants';

export interface WorkboardLanesStore {
  /** Keys of the lanes folded on this device. */
  collapsed: string[];
  /**
   * Whether the board's figures are unfolded on this device; `null` until the
   * person chose, and the screen's size then decides (shut on a phone).
   */
  summaryOpen: boolean | null;
  /**
   * Fold a lane, or unfold it.
   *
   * @param key - The lane.
   * @param known - Every lane the board draws right now; the rest is forgotten.
   */
  toggle: (key: string, known: readonly string[]) => void;
  /**
   * Keep what the person chose for the board's figures.
   *
   * @param open - Unfolded, or folded.
   */
  setSummaryOpen: (open: boolean) => void;
}

export const useWorkboardLanesStore = create<WorkboardLanesStore>()(
  persist(
    set => ({
      collapsed: [],
      summaryOpen: null,

      toggle: (key, known) =>
        set(state => {
          const kept = state.collapsed.filter(other => other !== key && known.includes(other));
          return { collapsed: state.collapsed.includes(key) ? kept : [...kept, key] };
        }),

      setSummaryOpen: open => set({ summaryOpen: open }),
    }),
    {
      name: WORKBOARD_LANES_PREFS_KEY,
      partialize: state => ({ collapsed: state.collapsed, summaryOpen: state.summaryOpen }),
      merge: (stored, current) => {
        // Whatever the storage holds is read, never trusted: a hand-edited or
        // half-written value must leave the board with every lane open and the
        // figures where the screen's size puts them.
        const saved = stored as { collapsed?: unknown; summaryOpen?: unknown } | undefined;
        return {
          ...current,
          collapsed: Array.isArray(saved?.collapsed)
            ? saved.collapsed.filter((key): key is string => typeof key === 'string')
            : [],
          summaryOpen: typeof saved?.summaryOpen === 'boolean' ? saved.summaryOpen : null,
        };
      },
    }
  )
);
