/**
 * How a horizontal scroll box reads its own overflow.
 *
 * One reading for every box that scrolls sideways inside a chat bubble — the
 * code block and the table — so the fade cue at the right edge means the same
 * thing on both. Pure, so the tolerance it rests on is testable without a
 * layout engine.
 */

/**
 * Pixels that may remain to the right and still count as « the end ». The
 * reserved scrollbar gutter is not part of the scrollable range: measured
 * 2026-09-17, the box stopped 10 px short of `scrollWidth - clientWidth`, so
 * an exact equality never turned the cue off.
 */
export const SCROLL_END_TOLERANCE_PX = 16;

/** The three numbers a scroll box exposes that the verdict depends on. */
export interface ScrollBoxMetrics {
  readonly clientWidth: number;
  readonly scrollWidth: number;
  readonly scrollLeft: number;
}

/** What a frame announces about its scroll box. */
export interface OverflowState {
  overflowing: boolean;
  scrolledEnd: boolean;
}

/**
 * Whether the box overflows sideways, and whether it is scrolled to its end.
 *
 * @param box - The scroll box (an element, or its measurements).
 * @returns The two facts the stylesheet's edge cue reads.
 */
export function readScrollBoxOverflow(box: ScrollBoxMetrics): OverflowState {
  const overflowing = box.scrollWidth > box.clientWidth + 1;
  const remaining = box.scrollWidth - (box.scrollLeft + box.clientWidth);
  return { overflowing, scrolledEnd: !overflowing || remaining <= SCROLL_END_TOLERANCE_PX };
}
