/**
 * Whether a chat table is drawn as a table or as a pile of cards (B2).
 *
 * Owner arbitration 2026-09-25: a table is stacked — one card per row, each
 * value under the name of its column — when it OVERFLOWS a container narrower
 * than {@link TABLE_STACK_MAX_CONTAINER_PX}. Wider, it stays a table and
 * scrolls sideways with a visible cue. Measured before the change: a five-column
 * answer drew 908 px wide in a 341 px phone bubble, two of its columns squeezed
 * to 40 px and one row 869 px tall.
 *
 * The decision is a small state machine rather than a comparison, because
 * stacking changes the very geometry it is decided on: drawn as cards, the
 * table fits, and reading that as « it fits now » would unstack it, make it
 * overflow again, and flicker. The natural width is therefore the one measured
 * while the table was still a table, and only a container that grows past it
 * (or past the threshold) turns the cards back into a table.
 */

import { readScrollBoxOverflow, type OverflowState, type ScrollBoxMetrics } from './scroll-box';

/** Below this container width, an overflowing table is drawn as stacked cards. */
export const TABLE_STACK_MAX_CONTAINER_PX = 480;

/** What the frame of a table says about how it is drawn. */
export interface TableLayout extends OverflowState {
  /** Drawn as cards, one per row. */
  stacked: boolean;
  /** Width of the table when drawn as a table; 0 until measured. */
  naturalWidth: number;
}

/** Before any measurement: a table, fitting. */
export const INITIAL_TABLE_LAYOUT: TableLayout = {
  stacked: false,
  naturalWidth: 0,
  overflowing: false,
  scrolledEnd: true,
};

/**
 * The layout after one reading of the table's scroll box.
 *
 * @param prev - The layout in force when the box was measured.
 * @param box - The scroll box around the table.
 * @returns The layout to draw next.
 */
export function nextTableLayout(prev: TableLayout, box: ScrollBoxMetrics): TableLayout {
  const containerWidth = box.clientWidth;
  // Drawn as cards, the box no longer says how wide the TABLE would be.
  const naturalWidth = prev.stacked ? prev.naturalWidth : box.scrollWidth;
  const stacked =
    containerWidth > 0 &&
    containerWidth < TABLE_STACK_MAX_CONTAINER_PX &&
    naturalWidth > containerWidth + 1;
  if (stacked) {
    return { stacked, naturalWidth, overflowing: false, scrolledEnd: true };
  }
  return { stacked, naturalWidth, ...readScrollBoxOverflow(box) };
}

/** Whether two layouts draw the same frame (the natural width is bookkeeping). */
export function sameTableLayout(a: TableLayout, b: TableLayout): boolean {
  return (
    a.stacked === b.stacked && a.overflowing === b.overflowing && a.scrolledEnd === b.scrolledEnd
  );
}
