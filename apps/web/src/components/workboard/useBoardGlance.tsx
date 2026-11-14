'use client';
/**
 * The board's figures above its filters, wired to the board under them
 * (ADR-276, amendment 2026-11-11).
 *
 * Kept out of the page for the reason `useBoardCategories` is: the page is the
 * place where every piece of the screen meets, and each piece it wires by hand
 * is a branch it carries. This one owns two decisions — WHEN the figures are
 * read again, and what pressing one does to the filters.
 */
import { useCallback, useState, type ReactNode } from 'react';

import { BoardGlance } from '@/components/workboard/BoardGlance';
import type { UseWorkboardResult } from '@/hooks/useWorkboard';
import type { Language } from '@/i18n/settings';
import { filtersFromParams, writeFilters } from '@/lib/workboard/filters-url';
import type { BoardFilters, TicketRow } from '@/types/workboard';

type BoardFigures = Pick<UseWorkboardResult, 'tickets' | 'firstLoad'>;

/**
 * How many times the board's rows were replaced: read again, or written.
 *
 * The figures are the WHOLE board's, and no count of the page says when they
 * moved: a due time that passes, a category renamed, a ticket handed to LIA
 * from another device move no column. So the figures are read whenever the
 * board is. Its reducer never mutates the rows — every payload (the poll, a
 * return to the tab, a filter, the re-read a dialog asks for) and every write
 * it applies hands the page a NEW array — so a new array is the witness.
 *
 * @param rows - The board's rows, as its hook hands them.
 * @returns A count that moves with each replacement, and with nothing else.
 */
export function useBoardReads(rows: readonly TicketRow[]): number {
  const [seen, setSeen] = useState(rows);
  const [reads, setReads] = useState(0);
  // Derived from the previous render, the way React documents it: set while
  // rendering, under a condition, so the count never trails the rows it counts.
  if (seen !== rows) {
    setSeen(rows);
    setReads(count => count + 1);
  }
  return reads;
}

export interface UseBoardGlanceOptions {
  lng: Language;
  board: BoardFigures;
  /**
   * Bumped by the page after each write that succeeded. The second witness:
   * a ticket the page does not carry — opened by its link under a filter that
   * hides it — changes a figure and not one row.
   */
  revision: number;
  /** Whether the screen has room for the block to arrive open. */
  wide: boolean;
  /** Hosted inside another interface: the block then arrives shut. */
  embedded: boolean;
  /** Replace the board's filters. */
  onFilters: (filters: BoardFilters) => void;
}

/**
 * @param options - The board, the screen and the way to its filters.
 * @returns The block to draw above the filters.
 */
export function useBoardGlance({
  lng,
  board,
  revision,
  wide,
  embedded,
  onFilters,
}: UseBoardGlanceOptions): ReactNode {
  const reads = useBoardReads(board.tickets);
  // ONE figure at a time: the narrowing replaces the filters, exactly as the
  // link each figure used to be opened the board on that figure alone. It
  // takes the road a link takes — written to a query, read back — so the
  // filters arrive in the ONE shape the page starts from: who holds and which
  // order stated at their defaults, as the first read of the board states them.
  const narrow = useCallback(
    (narrowing: BoardFilters) =>
      onFilters(filtersFromParams(writeFilters(new URLSearchParams(), narrowing))),
    [onFilters]
  );

  return (
    <BoardGlance
      lng={lng}
      defaultOpen={wide && !embedded}
      ready={!board.firstLoad}
      // The two counts side by side, never added: each one moving is a reason.
      stamp={`${revision}:${reads}`}
      onNarrow={narrow}
    />
  );
}
