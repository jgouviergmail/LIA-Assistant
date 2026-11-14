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
import {
  canFile,
  categoryOfLaneKey,
  knownCategories,
  laneOf,
  type LaneView,
} from '@/lib/workboard/lanes';
import type { TicketRow } from '@/types/workboard';

/** The droppable id a column registers. Prefixed so it cannot collide with a ticket id. */
export const COLUMN_DROPPABLE_PREFIX = 'workboard-column:';

/** The droppable id for one column. */
export function columnDroppableId(status: string): string {
  return `${COLUMN_DROPPABLE_PREFIX}${status}`;
}

/** The column a droppable id names, or null when it names something else. */
export function columnOfDroppable(id: string): string | null {
  return id.startsWith(COLUMN_DROPPABLE_PREFIX) ? id.slice(COLUMN_DROPPABLE_PREFIX.length) : null;
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
export function dragSpeech(t: (key: string, values: Record<string, string>) => string): DragSpeech {
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

// ---------------------------------------------------------------------------
// A board WITH lanes. A lane is a category; a cell is one lane of one column.
// Three things can be released over: a card, the empty part of a cell, and a
// lane's header. The position a drop resolves to is always the COLUMN's: the
// server keeps one order per column, and a lane is a filter over it.
// ---------------------------------------------------------------------------

/** The droppable id a cell registers: `workboard-cell:<lane>:<status>`. */
export const CELL_DROPPABLE_PREFIX = 'workboard-cell:';

/** The droppable id a lane's header registers. */
export const LANE_DROPPABLE_PREFIX = 'workboard-lane:';

/** The droppable id of one cell. Neither a lane key nor a status holds a colon. */
export function cellDroppableId(lane: string, status: string): string {
  return `${CELL_DROPPABLE_PREFIX}${lane}:${status}`;
}

/** The cell a droppable id names, or null when it names something else. */
export function cellOfDroppable(id: string): { lane: string; status: string } | null {
  if (!id.startsWith(CELL_DROPPABLE_PREFIX)) return null;
  const [lane, status] = id.slice(CELL_DROPPABLE_PREFIX.length).split(':');
  return lane && status ? { lane, status } : null;
}

/** The droppable id of one lane's header. */
export function laneDroppableId(lane: string): string {
  return `${LANE_DROPPABLE_PREFIX}${lane}`;
}

/** The lane a header's droppable id names, or null when it names something else. */
export function laneOfDroppable(id: string): string | null {
  return id.startsWith(LANE_DROPPABLE_PREFIX) ? id.slice(LANE_DROPPABLE_PREFIX.length) : null;
}

/**
 * Where a drop lands on a lane board.
 *
 * `lane` is the category the card is filed under by the drop — `null` for the
 * unfiled lane. It is ABSENT when the card stays in its lane: a move that
 * names no lane must leave the ticket filed where it was, never un-file it.
 */
export interface LaneDropTarget extends DropTarget {
  lane?: string | null;
}

/** The target, naming the lane only when the drop changes it. */
function laneTarget(
  status: string,
  position: number,
  from: string | null,
  to: string | null
): LaneDropTarget {
  return to === from ? { status, position } : { status, position, lane: to };
}

/**
 * Resolve a drop on a lane board into the move the API is asked for.
 *
 * @param activeId - The dragged ticket.
 * @param overId - What the pointer released over: a ticket id, a cell's
 *   droppable id, or a lane header's.
 * @param column - The cards of one column, in board order.
 * @param find - The row a ticket id names, or null when the board lost it.
 * @param known - The categories the board draws a lane for.
 * @returns The target, or null when nothing should be written.
 */
/** What every kind of drop reads: the card in the air and the board under it. */
interface DropScene {
  moving: TicketRow;
  /** The lane the card is drawn in. */
  from: string | null;
  column: (status: string) => readonly TicketRow[];
  known: ReadonlySet<string>;
}

/**
 * Released on a lane's HEADER: the card is filed there and nothing else — it
 * keeps its column and its place in it. Its own lane's header is where it
 * already is.
 */
function dropOnHeader(scene: DropScene, laneKeyOver: string): LaneDropTarget | null {
  const { moving, from, column } = scene;
  const to = categoryOfLaneKey(laneKeyOver);
  if (to === from) return null;
  const place = column(moving.status).findIndex(row => row.id === moving.id);
  return laneTarget(moving.status, Math.max(0, place), from, to);
}

/**
 * Released on the empty part of a CELL: the card goes after the last card of
 * that cell — in the column's order with the card itself left out, which is
 * the list the server inserts into. An empty cell has no neighbour to follow,
 * so the card goes to the end of the column.
 */
function dropOnCell(
  scene: DropScene,
  over: { lane: string; status: string }
): LaneDropTarget | null {
  const { moving, from, column, known } = scene;
  const to = categoryOfLaneKey(over.lane);
  // The empty part of its OWN cell: the card is already there.
  if (over.status === moving.status && to === from) return null;
  const others = column(over.status).filter(row => row.id !== moving.id);
  const last = others.findLastIndex(row => laneOf(row, known) === to);
  return laneTarget(over.status, last < 0 ? others.length : last + 1, from, to);
}

/** Released on another CARD: the card takes that card's place in its column. */
function dropOnCard(scene: DropScene, over: TicketRow): LaneDropTarget | null {
  const { moving, from, column, known } = scene;
  const to = laneOf(over, known);
  const target = column(over.status);
  const overIndex = target.findIndex(row => row.id === over.id);
  if (overIndex < 0) return null;
  // Same cell, same slot: nothing to write.
  const sameCell = over.status === moving.status && to === from;
  if (sameCell && target.findIndex(row => row.id === moving.id) === overIndex) return null;
  return laneTarget(over.status, overIndex, from, to);
}

export function resolveLaneDrop(
  activeId: string,
  overId: string | null,
  column: (status: string) => readonly TicketRow[],
  find: (id: string) => TicketRow | null,
  known: ReadonlySet<string>
): LaneDropTarget | null {
  if (!overId || overId === activeId) return null;
  const moving = find(activeId);
  if (!moving) return null;
  const scene: DropScene = { moving, from: laneOf(moving, known), column, known };

  const header = laneOfDroppable(overId);
  if (header !== null) return dropOnHeader(scene, header);
  const cell = cellOfDroppable(overId);
  if (cell !== null) return dropOnCell(scene, cell);
  const over = find(overId);
  return over ? dropOnCard(scene, over) : null;
}

/**
 * The move a drop on a lane board asks for — when the reader may make it.
 *
 * The category is the OWNER's: a ticket changes lane only when the reader owns
 * it, and only towards a lane of their own. The server refuses anything else;
 * this is the same rule, read BEFORE the write, so the board never sends a
 * move it knows will come back refused. A closed lane's targets are disabled
 * while a card is in the air, so this is the second lock, not the only one.
 *
 * @param activeId - The dragged ticket.
 * @param overId - What it was released over.
 * @param column - The cards of one column, in board order.
 * @param find - The row a ticket id names, or null when the board lost it.
 * @param lanes - The lanes drawn.
 * @param meId - The reader.
 * @returns The move, or null when there is nothing to write or no right to.
 */
export function laneMove(
  activeId: string,
  overId: string | null,
  column: (status: string) => readonly TicketRow[],
  find: (id: string) => TicketRow | null,
  lanes: readonly LaneView[],
  meId: string | undefined
): LaneDropTarget | null {
  const known = knownCategories(lanes);
  const target = resolveLaneDrop(activeId, overId, column, find, known);
  if (target === null || target.lane === undefined) return target;
  const moving = find(activeId);
  const lane = lanes.find(view => view.categoryId === target.lane);
  if (!moving || !lane) return null;
  return canFile(laneOf(moving, known), moving.owner_user_id === meId, lane) ? target : null;
}

/**
 * The column and the lane a droppable stands for.
 *
 * What the announcements read: on a lane board « where is it now » has two
 * halves, and each kind of target answers them differently.
 *
 * @param id - A cell's droppable id, a lane header's, or a ticket id.
 * @param find - The row a ticket id names, or null when the board lost it.
 * @param known - The categories the board draws a lane for.
 * @param movingStatus - The dragged card's column: a header keeps it.
 * @returns The place, or null for an id the board does not know.
 */
export function placeOf(
  id: string,
  find: (id: string) => TicketRow | null,
  known: ReadonlySet<string>,
  movingStatus: string
): { status: string; lane: string | null } | null {
  const cell = cellOfDroppable(id);
  if (cell !== null) return { status: cell.status, lane: categoryOfLaneKey(cell.lane) };
  const header = laneOfDroppable(id);
  if (header !== null) return { status: movingStatus, lane: categoryOfLaneKey(header) };
  const row = find(id);
  return row ? { status: row.status, lane: laneOf(row, known) } : null;
}

/** What a screen reader is told at each step of a drag on a lane board. */
export interface LaneSpeech {
  pickedUp: (title: string, column: string, lane: string) => string;
  movedOver: (title: string, column: string, lane: string) => string;
  dropped: (title: string, column: string, lane: string) => string;
  cancelled: (title: string) => string;
}

/**
 * Build the sentences a drag announces on a lane board.
 *
 * They name the lane AND the column: on this board a card moves in two
 * directions, and « moved to To do » no longer says where it went.
 *
 * @param t - The translator.
 * @returns One function per step of a drag.
 */
export function laneSpeech(t: (key: string, values: Record<string, string>) => string): LaneSpeech {
  return {
    pickedUp: (title, column, lane) => t('workboard.dnd.picked_up_lane', { title, column, lane }),
    movedOver: (title, column, lane) => t('workboard.dnd.moved_over_lane', { title, column, lane }),
    dropped: (title, column, lane) => t('workboard.dnd.dropped_lane', { title, column, lane }),
    cancelled: title => t('workboard.dnd.cancelled', { title }),
  };
}
