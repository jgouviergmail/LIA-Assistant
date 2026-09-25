'use client';

/**
 * Zustand store for the debug panel's width, as the person dragged it.
 *
 * The `persist` pattern of `shortcutsDockStore`: a display preference of the
 * device, outside the SEC-035 purge registry (see the key's rationale in
 * `lib/constants.ts`). The width is kept as chosen; the panel clamps it to what
 * the current window can hold (`components/debug/utils/panel-width.ts`).
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { DEBUG_PANEL_PREFS_KEY } from '@/lib/constants';

export interface DebugPanelStore {
  /** The width the person chose, or null for the default. */
  width: number | null;

  setWidth: (width: number) => void;
  reset: () => void;
}

export const useDebugPanelStore = create<DebugPanelStore>()(
  persist(
    set => ({
      width: null,

      setWidth: width => set({ width: Number.isFinite(width) ? Math.round(width) : null }),

      reset: () => set({ width: null }),
    }),
    {
      name: DEBUG_PANEL_PREFS_KEY,
      partialize: s => ({ width: s.width }),
    }
  )
);
