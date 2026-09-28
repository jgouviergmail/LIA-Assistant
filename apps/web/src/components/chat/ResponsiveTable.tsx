'use client';

/**
 * A table in a chat answer: a table where it fits, a scroll box with a visible
 * cue where it does not, a pile of cards on a narrow screen (B2).
 *
 * The frame carries three attributes the stylesheet reads — `data-stacked`,
 * `data-overflowing`, `data-scrolled-end` — and they are written to the DOM by
 * the layout effect rather than held in React state, for two reasons:
 *
 * - the first verdict is taken BEFORE the first paint (a layout effect), so a
 *   table that must be stacked is never shown wide for a frame, and doing that
 *   through `setState` inside the effect is the pattern the react-hooks
 *   ratchet refuses;
 * - a streaming answer re-renders the table on every token: attributes the
 *   component never declares in JSX are left alone by React, so a re-render
 *   cannot undo a verdict the measurement has not changed.
 *
 * A resize (a phone rotating, a panel opening, a column arriving mid-stream)
 * re-measures on the next animation frame. Doing it inside the ResizeObserver
 * callback itself would change the observed size during delivery — the
 * « ResizeObserver loop » error.
 */

import { useLayoutEffect, useRef, type ReactNode, type TableHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';
import {
  INITIAL_TABLE_LAYOUT,
  nextTableLayout,
  sameTableLayout,
  type TableLayout,
} from '@/lib/table-layout';

/** The frame attribute the stacked-card rules of the stylesheet key on. */
export const TABLE_STACKED_ATTRIBUTE = 'data-stacked';

function writeLayout(frame: HTMLElement, layout: TableLayout): void {
  frame.setAttribute(TABLE_STACKED_ATTRIBUTE, String(layout.stacked));
  frame.setAttribute('data-overflowing', String(layout.overflowing));
  frame.setAttribute('data-scrolled-end', String(layout.scrolledEnd));
}

/**
 * Keep the frame's layout attributes true to the scroll box's geometry.
 *
 * @param frameRef - The positioned frame the attributes are written on.
 * @param boxRef - The scroll box holding the table.
 */
function useTableLayoutAttributes(
  frameRef: React.RefObject<HTMLDivElement | null>,
  boxRef: React.RefObject<HTMLDivElement | null>
): void {
  useLayoutEffect(() => {
    const frame = frameRef.current;
    const box = boxRef.current;
    if (!frame || !box) return;

    let layout = INITIAL_TABLE_LAYOUT;
    const apply = (): void => {
      const next = nextTableLayout(layout, box);
      const changed = !sameTableLayout(layout, next);
      layout = next;
      if (changed) writeLayout(frame, layout);
    };
    writeLayout(frame, layout);
    apply();

    let frameId: number | null = null;
    const scheduleApply = (): void => {
      if (frameId !== null) return;
      frameId = requestAnimationFrame(() => {
        frameId = null;
        apply();
      });
    };
    box.addEventListener('scroll', apply, { passive: true });
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(scheduleApply);
    observer?.observe(box);
    // The box keeps its width when the TABLE widens (a column arriving
    // mid-stream): observing the table is what sees that.
    const table = box.firstElementChild;
    if (table) observer?.observe(table);

    return () => {
      box.removeEventListener('scroll', apply);
      observer?.disconnect();
      if (frameId !== null) cancelAnimationFrame(frameId);
    };
  }, [frameRef, boxRef]);
}

export interface ResponsiveTableProps extends TableHTMLAttributes<HTMLTableElement> {
  children?: ReactNode;
}

/**
 * The chat's `<table>`: its frame, its scroll box, and the table itself with
 * every attribute the pipeline gave it (roles, spans, a model's class).
 */
export function ResponsiveTable({ children, className, ...tableProps }: ResponsiveTableProps) {
  const frameRef = useRef<HTMLDivElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  useTableLayoutAttributes(frameRef, boxRef);

  return (
    <div ref={frameRef} className="table-frame my-3">
      <div ref={boxRef} className="table-wrapper rounded-lg border border-border/50 shadow-sm">
        <table {...tableProps} className={cn('divide-y divide-border/50', className)}>
          {children}
        </table>
      </div>
    </div>
  );
}
