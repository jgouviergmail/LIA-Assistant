/**
 * Where a dragged ticket actually lands (ADR-276).
 *
 * dnd-kit reports what the pointer is OVER — a card, or a column's empty space
 * — and the board has to turn that into the `{status, position}` the API
 * expects. Keeping the arithmetic here, pure, is what lets the awkward cases be
 * TESTED rather than discovered by dragging: dropping a card on itself, on the
 * empty part of its own column, above versus below a neighbour, or on a column
 * whose droppable id shares a prefix with a ticket id.
 */
import type { TicketRow } from '@/types/workboard';

/** The droppable id a column registers. Prefixed so it cannot collide with a ticket id. */
export const COLUMN_DROPPABLE_PREFIX = 'workboard-column:';

/** The droppable id for one column. */
export function columnDroppableId(status: string): string {
  return `${COLUMN_DROPPABLE_PREFIX}${status}`;
}

/** The column a droppable id names, or null when it names something else. */
export function columnOfDroppable(id: string): string | null {
  return id.startsWith(COLUMN_DROPPABLE_PREFIX)
    ? id.slice(COLUMN_DROPPABLE_PREFIX.length)
    : null;
}

/** Where a drop lands: which column, and at which index inside it. */
export interface DropTarget {
  status: string;
  position: number;
}

/**
 * Resolve a drop into the move the API is asked for.
 *
 * @param activeId - The dragged ticket.
 * @param overId - What the pointer released over: a ticket id, or a column
 *   droppable id when the pointer was over a column's empty space.
 * @param column - The cards of one column, in board order.
 * @param statusOf - The column a ticket currently sits in.
 * @returns The target, or null when nothing should be written — a drop outside
 *   any column, or one that would land the card exactly where it already is.
 */
export function resolveDrop(
  activeId: string,
  overId: string | null,
  column: (status: string) => readonly TicketRow[],
  statusOf: (id: string) => string | null
): DropTarget | null {
  if (!overId || overId === activeId) return null;

  const from = statusOf(activeId);
  if (from === null) return null;

  const overColumn = columnOfDroppable(overId);
  if (overColumn !== null) {
    // The empty part of a column: the card goes to the end of it. Dropping a
    // card on the empty space of its OWN column is not a move — it is already
    // there, and writing it would renumber the column for nothing.
    const target = column(overColumn);
    if (overColumn === from && target.some(row => row.id === activeId)) return null;
    return { status: overColumn, position: target.length };
  }

  const to = statusOf(overId);
  if (to === null) return null;

  const target = column(to);
  const overIndex = target.findIndex(row => row.id === overId);
  if (overIndex < 0) return null;

  if (to === from) {
    const fromIndex = target.findIndex(row => row.id === activeId);
    // Same column, same slot: nothing to write.
    if (fromIndex === overIndex) return null;
    return { status: to, position: overIndex };
  }

  return { status: to, position: overIndex };
}

/** What a screen reader is told at each step of a drag. */
export interface DragSpeech {
  pickedUp: (title: string, column: string) => string;
  movedOver: (title: string, column: string) => string;
  dropped: (title: string, column: string) => string;
  cancelled: (title: string) => string;
}

/**
 * Build the four sentences a drag announces.
 *
 * They name the COLUMN, never an index: « moved to position 3 » tells a
 * screen-reader user nothing about where their ticket went, which is the one
 * thing the announcement exists to say. Pure, so the wording is testable
 * without driving a pointer.
 *
 * @param t - The translator.
 * @returns One function per step of a drag.
 */
export function dragSpeech(
  t: (key: string, values: Record<string, string>) => string
): DragSpeech {
  return {
    pickedUp: (title, column) => t('workboard.dnd.picked_up', { title, column }),
    movedOver: (title, column) => t('workboard.dnd.moved_over', { title, column }),
    dropped: (title, column) => t('workboard.dnd.dropped', { title, column }),
    cancelled: title => t('workboard.dnd.cancelled', { title }),
  };
}

/**
 * The title of a ticket the board holds, or a bounded fallback.
 *
 * An announcement about « undefined » is worse than one about an id: the id at
 * least identifies the card the person is holding.
 *
 * @param id - The dragged ticket.
 * @param rows - Every row the board holds.
 * @returns The title, or the id when the row is gone.
 */
export function titleOf(id: string, rows: readonly TicketRow[]): string {
  return rows.find(row => row.id === id)?.title ?? id;
}
