/**
 * The board's state, as a pure function (ADR-276).
 *
 * A kanban has to answer a drag before the server does, or every card lags a
 * round trip behind the finger. That optimism is exactly where a board starts
 * lying: a counter drifting one at a time, a card landing at the wrong index,
 * a rollback that restores membership but not ORDER. Keeping it here — pure,
 * no I/O, no React — is what makes each of those a test rather than a bug
 * report.
 *
 * Two rules the actions below are built around:
 *
 * - **A counter is the SERVER's aggregate** (ADR-185), never the length of the
 *   page: `counts_by_status` covers columns whose cards this page does not
 *   carry. So a move ADJUSTS the two counters it provably changed, and nothing
 *   else recomputes them from the rows.
 * - **Creation and deletion do not live here.** They change rows this page
 *   cannot see (a child in another column, a row past the page), so they are
 *   followed by a refetch — a count nobody can compute exactly is a count that
 *   must be re-read.
 */
import type { BoardPage, TicketRow } from '@/types/workboard';

export interface WorkboardState {
  tickets: TicketRow[];
  /** Exact count per column, from the server's aggregate over the same filter. */
  countsByStatus: Record<string, number>;
  /** Exact number of tickets the filter matches, page or no page. */
  total: number;
}

export type WorkboardAction =
  | { type: 'loaded'; page: BoardPage }
  | { type: 'moved'; id: string; status: string; position: number }
  | { type: 'restored'; snapshot: WorkboardState }
  | { type: 'patched'; ticket: TicketRow };

export const initialWorkboardState: WorkboardState = {
  tickets: [],
  countsByStatus: {},
  total: 0,
};

/**
 * The cards of one column, in board order.
 *
 * Ordered by `position` and then by `id`, so the order is TOTAL: two rows
 * sharing a position (a server that has not re-numbered yet, a page assembled
 * mid-move) would otherwise swap between two renders and make the list flicker.
 *
 * @param state - The board.
 * @param status - The column.
 * @returns Its cards, ordered; an empty list for a column with none.
 */
export function ticketsOf(state: WorkboardState, status: string): TicketRow[] {
  return state.tickets
    .filter(row => row.status === status)
    .sort((left, right) => left.position - right.position || left.id.localeCompare(right.id));
}

/** Shift a counter without ever letting it go negative. */
function bump(counts: Record<string, number>, status: string, delta: number): void {
  counts[status] = Math.max(0, (counts[status] ?? 0) + delta);
}

/**
 * Place a card at an index inside its (new) column and re-number that column.
 *
 * @param state - The board before the move.
 * @param id - The card being moved.
 * @param status - The column it lands in.
 * @param position - Where in that column, clamped to its length.
 * @returns The board after the move.
 */
function applyMove(
  state: WorkboardState,
  id: string,
  status: string,
  position: number
): WorkboardState {
  const moving = state.tickets.find(row => row.id === id);
  // A card a peer deleted a second ago, or a stale drag: a move that invents a
  // row would put a ghost on the board.
  if (!moving) return state;

  const from = moving.status;

  // The destination column with the card inserted where it was dropped, and
  // the source column without it. Both are re-numbered DENSELY, which is what
  // makes the inverse move land the card exactly where it came from — the
  // property the rollback relies on.
  const destination = ticketsOf(state, status).filter(row => row.id !== id);
  destination.splice(Math.max(0, Math.min(position, destination.length)), 0, moving);
  const source = from === status ? [] : ticketsOf(state, from).filter(row => row.id !== id);

  const placement = new Map<string, { status: string; position: number }>();
  destination.forEach((row, index) => placement.set(row.id, { status, position: index }));
  source.forEach((row, index) => placement.set(row.id, { status: from, position: index }));

  const counts = { ...state.countsByStatus };
  if (from !== status) {
    bump(counts, from, -1);
    bump(counts, status, 1);
  }

  return {
    ...state,
    tickets: state.tickets.map(row => {
      const placed = placement.get(row.id);
      return placed ? { ...row, ...placed } : row;
    }),
    countsByStatus: counts,
  };
}

/**
 * Advance the board's state.
 *
 * @param state - Where the board is.
 * @param action - What happened.
 * @returns The new state; the SAME object when nothing applied, so React skips
 *   the render.
 */
export function workboardReducer(
  state: WorkboardState,
  action: WorkboardAction
): WorkboardState {
  switch (action.type) {
    case 'loaded':
      return {
        tickets: action.page.tickets,
        countsByStatus: { ...action.page.counts_by_status },
        total: action.page.total,
      };

    case 'moved':
      return applyMove(state, action.id, action.status, action.position);

    case 'restored':
      return action.snapshot;

    case 'patched': {
      const previous = state.tickets.find(row => row.id === action.ticket.id);
      if (!previous) return state;
      const counts = { ...state.countsByStatus };
      // The status `<select>` on a card goes through PATCH rather than move, so
      // the counters have to follow a patch exactly as they follow a drag.
      if (previous.status !== action.ticket.status) {
        bump(counts, previous.status, -1);
        bump(counts, action.ticket.status, 1);
      }
      return {
        ...state,
        tickets: state.tickets.map(row => (row.id === action.ticket.id ? action.ticket : row)),
        countsByStatus: counts,
      };
    }
  }
}
