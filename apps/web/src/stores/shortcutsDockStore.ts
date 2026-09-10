'use client';

/**
 * Zustand store for the shortcuts dock's display preferences (ADR-277).
 *
 * The position (viewport percentages, so the dock survives resolution and
 * orientation changes) and whether it is folded — the `persist` pattern of
 * `eyesWidgetStore`. A pure display preference of the device: deliberately
 * outside the SEC-035 purge registry (see the key's rationale in
 * `lib/constants.ts`). WHAT is pinned lives on the account, never here.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { FloatingPosition } from '@/hooks/useFloatingDrag';
import { SHORTCUTS_DOCK_PREFS_KEY } from '@/lib/constants';

export interface ShortcutsDockStore {
  /** Custom position, or null for the default spot at the right edge. */
  position: FloatingPosition | null;
  /** Folded into its restore button. */
  minimized: boolean;

  setPosition: (position: FloatingPosition) => void;
  setMinimized: (minimized: boolean) => void;
  reset: () => void;
}

const DEFAULTS = {
  position: null as FloatingPosition | null,
  minimized: false,
};

function clampPct(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export const useShortcutsDockStore = create<ShortcutsDockStore>()(
  persist(
    set => ({
      ...DEFAULTS,

      setPosition: position =>
        set({ position: { xPct: clampPct(position.xPct), yPct: clampPct(position.yPct) } }),

      setMinimized: minimized => set({ minimized }),

      reset: () => set(DEFAULTS),
    }),
    {
      name: SHORTCUTS_DOCK_PREFS_KEY,
      partialize: s => ({ position: s.position, minimized: s.minimized }),
    }
  )
);
