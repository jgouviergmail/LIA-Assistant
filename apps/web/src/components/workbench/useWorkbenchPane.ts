'use client';

/**
 * One « Tools » pane a person sizes by hand on a large screen (owner request
 * 2026-10-31): its id, the width it draws and the props of its separator.
 *
 * A pane nobody sized keeps its layout's own responsive widths, and its
 * separator starts from the width it is drawn at. Once sized, it draws the
 * chosen width (`--pane-w`, the caller's `lg:`/`xl:` class applies it) — clamped
 * to what its row holds now and kept as chosen, so a wider window gets it back.
 * The width is a preference of the DEVICE (`workbenchPanesStore`).
 */
import { useId, useLayoutEffect, useState, type CSSProperties } from 'react';

import type { PaneSeparatorProps } from '@/components/ui/pane-separator';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { clampPaneWidth } from '@/lib/pane-width';
import {
  WORKBENCH_PANES,
  WORKBENCH_PANE_STEP,
  paneBounds,
  type WorkbenchPane,
} from '@/lib/workbench/panes';
import { useWorkbenchPanesStore } from '@/stores/workbenchPanesStore';

export interface WorkbenchPaneState {
  /** Spread on the pane element (its row must be its parent). */
  pane: { id: string; ref: (node: HTMLElement | null) => void; style?: CSSProperties };
  /** The person sized it: the pane draws `--pane-w` instead of its layout's widths. */
  resized: boolean;
  /** Spread on the pane's `PaneSeparator`. */
  separator: Omit<PaneSeparatorProps, 'className'>;
}

/** The width a sized pane draws from a breakpoint on (literal classes, for Tailwind's scan). */
const SIZED_WIDTH = {
  lg: 'lg:w-[var(--pane-w)] lg:flex-none',
  xl: 'xl:w-[var(--pane-w)] xl:flex-none',
} as const;

/**
 * A pane's width classes: the chosen width once sized, its layout's own until then.
 *
 * @param state - The pane's state (absent where the caller sizes nothing).
 * @param layout - The layout's own width classes.
 * @param from - The breakpoint from which the pane sits beside its neighbour.
 */
export function paneWidth(
  state: WorkbenchPaneState | undefined,
  layout: string,
  from: keyof typeof SIZED_WIDTH = 'lg'
): string {
  return state?.resized ? SIZED_WIDTH[from] : layout;
}

/** Where a pane's separator sits: on the border between two panes, its hit area over both. */
export const PANE_SEPARATOR_CLASS = 'relative -mx-1.5 w-3 shrink-0';

export function useWorkbenchPane(lng: Language, name: WorkbenchPane): WorkbenchPaneState {
  const { t } = useTranslation(lng);
  const spec = WORKBENCH_PANES[name];
  const stored = useWorkbenchPanesStore(state => state.widths[name]);
  const setWidth = useWorkbenchPanesStore(state => state.setWidth);
  const reset = useWorkbenchPanesStore(state => state.reset);
  const id = useId();
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [measured, setMeasured] = useState({ pane: 0, row: 0 });

  // Measure the pane and the row holding it, and follow both: a resized window,
  // a pane opening beside it, or the pane's own new width.
  useLayoutEffect(() => {
    const row = node?.parentElement;
    if (!node || !row) return;
    const measure = () =>
      setMeasured({
        pane: node.getBoundingClientRect().width,
        row: row.getBoundingClientRect().width,
      });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    observer.observe(row);
    return () => observer.disconnect();
  }, [node]);

  const bounds = paneBounds(spec, measured.row);
  const width = clampPaneWidth(stored ?? (measured.pane || spec.initial), bounds);
  return {
    pane: {
      id,
      ref: setNode,
      style: stored === undefined ? undefined : ({ '--pane-w': `${width}px` } as CSSProperties),
    },
    resized: stored !== undefined,
    separator: {
      edge: spec.edge,
      width,
      bounds,
      step: WORKBENCH_PANE_STEP,
      label: t(spec.labelKey),
      controls: id,
      onResize: next => setWidth(name, next),
      onReset: () => reset(name),
    },
  };
}
