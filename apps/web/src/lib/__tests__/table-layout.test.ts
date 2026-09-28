/**
 * How a chat table decides to be a scroll box or a pile of cards (B2, owner
 * arbitration 2026-09-25: « stacked when it overflows a container narrower
 * than 480 px »).
 *
 * The decision is pure so its one subtle property can be pinned without a
 * layout engine: once stacked, the drawn table no longer reveals how wide it
 * WOULD be, so the verdict must rest on the width measured while it was still
 * a table — otherwise it stacks, fits, unstacks, overflows, and flickers.
 */
import { describe, expect, it } from 'vitest';

import { readScrollBoxOverflow, SCROLL_END_TOLERANCE_PX } from '../scroll-box';
import {
  INITIAL_TABLE_LAYOUT,
  nextTableLayout,
  TABLE_STACK_MAX_CONTAINER_PX,
  type TableLayout,
} from '../table-layout';

function box(clientWidth: number, scrollWidth: number, scrollLeft = 0) {
  return { clientWidth, scrollWidth, scrollLeft };
}

describe('readScrollBoxOverflow', () => {
  it('reads a box that fits as not overflowing and at its end', () => {
    expect(readScrollBoxOverflow(box(300, 300))).toEqual({
      overflowing: false,
      scrolledEnd: true,
    });
  });

  it('ignores a one-pixel rounding difference', () => {
    expect(readScrollBoxOverflow(box(300, 301)).overflowing).toBe(false);
  });

  it('reads an overflowing box scrolled to its start as not at its end', () => {
    expect(readScrollBoxOverflow(box(300, 900))).toEqual({
      overflowing: true,
      scrolledEnd: false,
    });
  });

  it('counts the reserved gutter as the end (the box stops short of the exact end)', () => {
    const lastPixels = 900 - 300 - (SCROLL_END_TOLERANCE_PX - 2);
    expect(readScrollBoxOverflow(box(300, 900, lastPixels)).scrolledEnd).toBe(true);
  });
});

describe('nextTableLayout', () => {
  const narrow = TABLE_STACK_MAX_CONTAINER_PX - 139; // a 341 px phone bubble

  it('keeps a table that fits a narrow container as a table', () => {
    const next = nextTableLayout(INITIAL_TABLE_LAYOUT, box(narrow, narrow));
    expect(next.stacked).toBe(false);
    expect(next.overflowing).toBe(false);
  });

  it('stacks a table that overflows a narrow container', () => {
    const next = nextTableLayout(INITIAL_TABLE_LAYOUT, box(narrow, 908));
    expect(next).toMatchObject({ stacked: true, naturalWidth: 908, overflowing: false });
  });

  it('never stacks at or above the threshold: a wide container scrolls instead', () => {
    const next = nextTableLayout(
      INITIAL_TABLE_LAYOUT,
      box(TABLE_STACK_MAX_CONTAINER_PX, TABLE_STACK_MAX_CONTAINER_PX + 400)
    );
    expect(next).toMatchObject({ stacked: false, overflowing: true, scrolledEnd: false });
  });

  it('stays stacked while stacking made it fit (the drawn width is no longer the natural one)', () => {
    const stacked = nextTableLayout(INITIAL_TABLE_LAYOUT, box(narrow, 908));
    // Drawn as cards, the box no longer overflows: that must NOT unstack it.
    const again = nextTableLayout(stacked, box(narrow, narrow));
    expect(again).toMatchObject({ stacked: true, naturalWidth: 908 });
  });

  it('unstacks when the container grows past the natural width', () => {
    const stacked = nextTableLayout(INITIAL_TABLE_LAYOUT, box(narrow, 420));
    const wider = nextTableLayout(stacked, box(440, 440));
    expect(wider.stacked).toBe(false);
  });

  it('unstacks when the container reaches the threshold, then re-measures as a table', () => {
    const stacked = nextTableLayout(INITIAL_TABLE_LAYOUT, box(narrow, 908));
    const unstacked = nextTableLayout(stacked, box(TABLE_STACK_MAX_CONTAINER_PX, 908));
    expect(unstacked.stacked).toBe(false);
    // The next reading, now drawn as a table, measures the real natural width.
    const measured = nextTableLayout(unstacked, box(TABLE_STACK_MAX_CONTAINER_PX, 911));
    expect(measured).toMatchObject({ stacked: false, naturalWidth: 911, overflowing: true });
  });

  it('never stacks a box that is not laid out (zero width: hidden, or no layout engine)', () => {
    const next: TableLayout = nextTableLayout(INITIAL_TABLE_LAYOUT, box(0, 500));
    expect(next.stacked).toBe(false);
  });
});
