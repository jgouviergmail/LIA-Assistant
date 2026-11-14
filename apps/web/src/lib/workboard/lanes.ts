/**
 * The board's lanes, as a pure model (ADR-276).
 *
 * A lane is a CATEGORY: a name the owner of a board files tickets under. The
 * board draws one row per lane across its columns, and a ticket filed under
 * nothing sits in the unfiled lane. The server sends the lanes with their
 * exact counts (`BoardPage.lanes`); everything here turns that into what the
 * screen draws, with no I/O and no React, so each rule is a test.
 *
 * Four rules, each of them a way the lanes would otherwise lie or lose
 * something:
 *
 * - **No lane, no change.** A reader with no category in sight gets an empty
 *   list, and the board draws exactly what it drew before categories existed.
 * - **An empty lane stays, unless a filter emptied it.** With nothing
 *   narrowing the board an empty lane is a drop target and a reminder that
 *   the category exists; under a filter it is a row that says « no match »
 *   six times, so it is not drawn.
 * - **A ticket never falls between two lanes.** One whose category is not on
 *   the board — deleted a moment ago, the page not yet re-read — is shown in
 *   the unfiled lane, where the server is about to put it.
 * - **The category is the OWNER's** (owner arbitration, 2026-11-11). A ticket
 *   moves freely inside its own lane; it changes lane only when the reader
 *   owns it, and only towards the unfiled lane or a lane of their own. This
 *   mirrors the service's refusal: a lane the server would refuse is never
 *   offered.
 */
import type { CategoryOption, LaneRow, TicketRow } from '@/types/workboard';

/** The key of the lane of tickets filed under nothing. */
export const UNFILED_LANE = 'unfiled';

/** A lane's key in the DOM and in the device's memory. */
export function laneKey(categoryId: string | null): string {
  return categoryId ?? UNFILED_LANE;
}

/** The category a lane key names; null for the unfiled lane. */
export function categoryOfLaneKey(key: string): string | null {
  return key === UNFILED_LANE ? null : key;
}

/** One lane as the board draws it. */
export interface LaneView {
  key: string;
  /** The category; null for the unfiled lane. */
  categoryId: string | null;
  /** The category's name; null for the unfiled lane, which the locale names. */
  name: string | null;
  /** Whose category; null for the unfiled lane. */
  ownerUserId: string | null;
  /** The reader may file their own tickets here, and manage it when it is a category. */
  mine: boolean;
  /** EXACT count per column, from the server's aggregate (ADR-185). */
  countsByStatus: Record<string, number>;
  /** EXACT number of tickets in the lane — the sum of its columns. */
  total: number;
  /** Index among the lanes DRAWN: the alternating ground reads its parity. */
  stripe: number;
}

/**
 * The lanes to draw, in the server's order.
 *
 * @param lanes - The lanes of the page, as the API sent them.
 * @param meId - The reader.
 * @param narrowed - Whether a filter narrows the board.
 * @returns One view per lane drawn; empty when the board has no lane at all.
 */
export function laneViews(
  lanes: readonly LaneRow[],
  meId: string | undefined,
  narrowed: boolean
): LaneView[] {
  return lanes
    .map(lane => ({
      key: laneKey(lane.category_id),
      categoryId: lane.category_id,
      name: lane.name,
      ownerUserId: lane.owner_user_id,
      mine: lane.category_id === null || lane.owner_user_id === meId,
      countsByStatus: lane.counts_by_status,
      total: Object.values(lane.counts_by_status).reduce((sum, count) => sum + count, 0),
    }))
    .filter(lane => !narrowed || lane.total > 0)
    .map((lane, stripe) => ({ ...lane, stripe }));
}

/** Between a category and whose it is; the mark the cards put between two facts. */
const JOIN = ' · ';

/** A lane that is a category — the unfiled lane has no id and no name. */
function isCategory(lane: LaneRow): lane is LaneRow & { category_id: string; name: string } {
  return lane.category_id !== null && lane.name !== null;
}

/**
 * The reader's OWN categories, in their order.
 *
 * The only lanes one of their tickets may be filed under (the category is the
 * owner's), read from the board's own payload: the lanes name every category
 * in sight, empty ones included.
 *
 * @param lanes - The lanes of the page, as the API sent them.
 * @param meId - The reader.
 * @returns Their categories; empty for a reader the page cannot identify.
 */
export function ownCategories(
  lanes: readonly LaneRow[],
  meId: string | undefined
): CategoryOption[] {
  return lanes
    .filter(isCategory)
    .filter(lane => lane.owner_user_id === meId)
    .map(lane => ({ id: lane.category_id, name: lane.name }));
}

/**
 * Every category the board can be narrowed to.
 *
 * Somebody else's category says whose it is: two people may both have a
 * « Home », and a list offering the same word twice is a coin toss.
 *
 * @param lanes - The lanes of the page, as the API sent them.
 * @param meId - The reader.
 * @param ownerName - How the owner of a category reads.
 * @returns One option per category, in the lanes' order.
 */
export function laneOptions(
  lanes: readonly LaneRow[],
  meId: string | undefined,
  ownerName: (userId: string) => string
): CategoryOption[] {
  return lanes.filter(isCategory).map(lane => ({
    id: lane.category_id,
    name:
      lane.owner_user_id === null || lane.owner_user_id === meId
        ? lane.name
        : `${lane.name}${JOIN}${ownerName(lane.owner_user_id)}`,
  }));
}

/**
 * The name of a category of the board.
 *
 * @param lanes - The lanes of the page, as the API sent them.
 * @returns A lookup answering undefined for a category the board does not carry.
 */
export function categoryNamer(
  lanes: readonly LaneRow[]
): (categoryId: string) => string | undefined {
  return categoryId => lanes.find(lane => lane.category_id === categoryId)?.name ?? undefined;
}

/**
 * The categories the board draws a lane for.
 *
 * @param lanes - The lanes drawn.
 * @returns Their categories — the unfiled lane has none.
 */
export function knownCategories(lanes: readonly Pick<LaneView, 'categoryId'>[]): Set<string> {
  return new Set(lanes.flatMap(lane => (lane.categoryId === null ? [] : [lane.categoryId])));
}

/**
 * The lane a ticket is DRAWN in.
 *
 * @param ticket - The row.
 * @param known - The categories on the board.
 * @returns Its category, or null — for a ticket filed under nothing, and for
 *   one whose category the board no longer carries.
 */
export function laneOf(
  ticket: Pick<TicketRow, 'category_id'>,
  known: ReadonlySet<string>
): string | null {
  return ticket.category_id !== null && known.has(ticket.category_id) ? ticket.category_id : null;
}

/**
 * The cards of one cell — one lane of one column — in the column's own order.
 *
 * @param column - The cards of the column, in board order.
 * @param categoryId - The lane; null for the unfiled one.
 * @param known - The categories on the board.
 * @returns The lane's share of the column.
 */
export function ticketsOfCell(
  column: readonly TicketRow[],
  categoryId: string | null,
  known: ReadonlySet<string>
): TicketRow[] {
  return column.filter(row => laneOf(row, known) === categoryId);
}

/**
 * Whether a ticket may land in a lane.
 *
 * @param from - The lane the ticket is drawn in.
 * @param ownsTicket - Whether the reader owns the ticket.
 * @param lane - The lane it would land in.
 * @returns True for its own lane, and for the reader's lanes when they own it.
 */
export function canFile(
  from: string | null,
  ownsTicket: boolean,
  lane: Pick<LaneView, 'categoryId' | 'mine'>
): boolean {
  return lane.categoryId === from || (ownsTicket && lane.mine);
}

/**
 * The write that files a ticket under a lane.
 *
 * `null` and « unchanged » are the same wire value, so leaving a category is
 * said explicitly — the dates' own convention.
 *
 * @param categoryId - The lane; null for the unfiled one.
 * @returns The fields to send.
 */
export function lanePatch(
  categoryId: string | null
): { category_id: string } | { clear_category: true } {
  return categoryId === null ? { clear_category: true } : { category_id: categoryId };
}
