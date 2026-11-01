'use client';

/**
 * A grid of days walked with the keyboard (ADR-369, Task 5b.1; the WAI-ARIA
 * grid pattern): ONE cell is in the tab order, the arrows move it by a day or
 * a week, Home and End to its week's first and last day — never past the grid.
 */
import { useCallback, useRef, useState, type KeyboardEvent } from 'react';

const WEEK = 7;

/** What moves the focus, and by how much (Home/End are relative to the week). */
function target(key: string, index: number, count: number): number | null {
  const weekStart = index - (index % WEEK);
  const moves: Record<string, number> = {
    ArrowLeft: index - 1,
    ArrowRight: index + 1,
    ArrowUp: index - WEEK,
    ArrowDown: index + WEEK,
    Home: weekStart,
    End: weekStart + WEEK - 1,
  };
  const next = moves[key];
  return next === undefined ? null : Math.min(count - 1, Math.max(0, next));
}

export interface RovingGrid {
  /** The cell in the tab order. */
  focused: number;
  /** Each cell's props: its place in the tab order, its ref, its keys. */
  cell: (index: number) => {
    tabIndex: number;
    ref: (element: HTMLElement | null) => void;
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
    onFocus: () => void;
  };
}

/**
 * @param count - The cells of the grid.
 * @param initial - The cell in the tab order at first (today, or the day shown).
 */
export function useRovingGrid(count: number, initial: number): RovingGrid {
  const [focused, setFocused] = useState(initial);
  const cells = useRef(new Map<number, HTMLElement>());
  const current = Math.min(count - 1, Math.max(0, focused));
  const cell = useCallback(
    (index: number) => ({
      tabIndex: index === current ? 0 : -1,
      ref: (element: HTMLElement | null) => {
        if (element) cells.current.set(index, element);
        else cells.current.delete(index);
      },
      onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
        const next = target(event.key, index, count);
        if (next === null) return;
        event.preventDefault();
        setFocused(next);
        cells.current.get(next)?.focus();
      },
      onFocus: () => setFocused(index),
    }),
    [count, current]
  );
  return { focused: current, cell };
}
