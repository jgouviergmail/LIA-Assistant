'use client';

/**
 * Zustand store for the « Tools » panes' widths, as the person dragged them
 * (owner request 2026-10-31).
 *
 * The `persist` pattern of `debugPanelStore`: a display preference of the
 * device, outside the SEC-035 purge registry (see the key's rationale in
 * `lib/constants.ts`). A width is kept as chosen; the pane clamps it to what the
 * current row can hold (`lib/workbench/panes.ts`). Read back, only a declared
 * pane holding a number survives — a renamed pane or a hand-edited value is
 * dropped rather than trusted.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { WORKBENCH_PANES_PREFS_KEY } from '@/lib/constants';
import { isWorkbenchPane, type WorkbenchPane } from '@/lib/workbench/panes';

type PaneWidths = Partial<Record<WorkbenchPane, number>>;

export interface WorkbenchPanesStore {
  /** The widths the person chose; a pane absent keeps its layout's own. */
  widths: PaneWidths;

  setWidth: (pane: WorkbenchPane, width: number) => void;
  reset: (pane: WorkbenchPane) => void;
}

/** The declared panes holding a finite number, from whatever was stored. */
function readWidths(stored: unknown): PaneWidths {
  if (typeof stored !== 'object' || stored === null) return {};
  const widths: PaneWidths = {};
  for (const [pane, width] of Object.entries(stored)) {
    if (isWorkbenchPane(pane) && typeof width === 'number' && Number.isFinite(width)) {
      widths[pane] = Math.round(width);
    }
  }
  return widths;
}

export const useWorkbenchPanesStore = create<WorkbenchPanesStore>()(
  persist(
    set => ({
      widths: {},

      setWidth: (pane, width) => {
        if (!Number.isFinite(width)) return;
        set(state => ({ widths: { ...state.widths, [pane]: Math.round(width) } }));
      },

      reset: pane =>
        set(state => {
          const widths = { ...state.widths };
          delete widths[pane];
          return { widths };
        }),
    }),
    {
      name: WORKBENCH_PANES_PREFS_KEY,
      partialize: state => ({ widths: state.widths }),
      merge: (persisted, current) => ({
        ...current,
        widths: readWidths((persisted as { widths?: unknown } | undefined)?.widths),
      }),
    }
  )
);
