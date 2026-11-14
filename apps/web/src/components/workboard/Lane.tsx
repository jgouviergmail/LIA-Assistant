'use client';
/**
 * One lane of the board: a category, across the columns (ADR-276).
 *
 * A lane is a header and, under it, one cell per column drawn. Three things
 * here are decisions, not styling:
 *
 * - **The ground alternates, and the cards take the opposite one.** Lanes are
 *   told apart by their name and by a ground that alternates from one to the
 *   next — never by a colour per category (owner, 2026-11-11). A lane on the
 *   card ground holds its cards on the background and a lane on the
 *   background holds them on the card ground: the two grounds, whole, at every
 *   level (owner directive, 2026-11-08).
 * - **An empty lane is its header, and its header is a drop target.** A lane
 *   that holds nothing draws no row of empty cells; releasing a card on its
 *   header files the card there and leaves it in its column.
 * - **A lane the dragged card may not enter is closed, visibly.** The category
 *   is the OWNER's: a ticket changes lane only when the reader owns it, and
 *   only towards their own lanes. A closed lane is dimmed and none of its
 *   targets accept the drop — the board never offers what the server refuses.
 *
 * - **A thin rule marks each column off the one before it.** With six columns
 *   across and a ground per lane, nothing said where a column ended (owner,
 *   2026-11-11). The rule is the neutral line colour, one pixel, in the gap —
 *   drawn by the cell that opens the column, so the names' row above and every
 *   lane rule at the same place. Only where several columns are drawn.
 *
 * A cell's count is the SERVER's (ADR-185): when it holds more tickets than
 * this page carries, it says how many are not on the page rather than letting
 * its lane's header disagree with what is under it.
 */
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { SortableCard, type CardHandlers } from '@/components/workboard/Column';
import { TicketCard } from '@/components/workboard/TicketCard';
import { ChevronDown, ChevronRight, Plus } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { partyLabel, type PeerName } from '@/lib/workboard/display';
import { cellDroppableId, laneDroppableId } from '@/lib/workboard/dnd';
import { laneIcon, partyIcon } from '@/lib/workboard/icons';
import type { LaneView } from '@/lib/workboard/lanes';
import type { TicketRow } from '@/types/workboard';

/**
 * The rule between two columns: a hairline in the middle of the grid's gap.
 *
 * The cell that OPENS a column draws it, to its own left — `-left-1.5` is half
 * the `gap-3` the names' row and every lane share. `reach` is how far it runs
 * past the cell, into the padding of the row it stands in, so that it meets
 * the line under it instead of stopping short.
 */
export function ColumnRule({ reach }: { reach: string }) {
  return (
    <span
      aria-hidden="true"
      data-column-rule=""
      className={cn('pointer-events-none absolute -left-1.5 w-px bg-border', reach)}
    />
  );
}

/** The ground of a lane, by its place among the lanes drawn. */
export function laneGround(stripe: number): 'card' | 'background' {
  return stripe % 2 === 0 ? 'card' : 'background';
}

/** The DOM id of a lane's body, which its fold button controls. */
function bodyId(lane: LaneView): string {
  return `wb-lane-body-${lane.key}`;
}

/** Who a lane belongs to, when it is not the reader's — « from Marie ». */
function LaneOwner({ lane, peers }: { lane: LaneView; peers: readonly PeerName[] }) {
  const { t } = useTranslation();
  if (lane.mine || lane.ownerUserId === null) return null;
  const peer = peers.find(connection => connection.peer_id === lane.ownerUserId);
  const name = partyLabel(
    peer ? { kind: 'peer', name: peer.peer_display_name } : { kind: 'unknown' },
    t
  );
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
      {partyIcon(peer ? 'peer' : 'unknown', 'h-3 w-3')}
      {t('workboard.party.owned_by', { name })}
    </span>
  );
}

interface LaneHeaderProps {
  lane: LaneView;
  name: string;
  /** The EXACT number of tickets the header states. */
  count: number;
  peers: readonly PeerName[];
  /** Whether the lane has a body to fold at all. */
  foldable: boolean;
  folded: boolean;
  /** Whether the dragged card may land here. */
  open: boolean;
  /** Stick under the application header — the phone, where the page scrolls. */
  pinned: boolean;
  onToggle: () => void;
  onAdd?: (categoryId: string | null) => void;
}

function LaneHeader({
  lane,
  name,
  count,
  peers,
  foldable,
  folded,
  open,
  pinned,
  onToggle,
  onAdd,
}: LaneHeaderProps) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: laneDroppableId(lane.key), disabled: !open });
  return (
    <header
      ref={setNodeRef}
      className={cn(
        'px-3 py-2',
        // On a phone the page scrolls and the lane's name must stay in sight:
        // pinned under the application header, on the lane's own ground so the
        // cards pass beneath it.
        pinned && 'sticky top-16 z-10',
        pinned && (laneGround(lane.stripe) === 'card' ? 'bg-card' : 'bg-background'),
        isOver && 'bg-primary/5'
      )}
    >
      {/* Sticks to the left edge of the board's own scroller, so the name of a
          lane stays readable while the columns scroll under it. */}
      <div className="sticky left-3 flex w-max max-w-full items-center gap-2">
        {foldable ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            aria-expanded={!folded}
            aria-controls={bodyId(lane)}
            aria-label={t(folded ? 'workboard.lanes.expand' : 'workboard.lanes.collapse', { name })}
            onClick={onToggle}
          >
            {folded ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
        ) : (
          // Nothing to fold: the same width, so every lane's name starts on
          // the same line whether or not it holds a ticket.
          <span className="h-8 w-8 shrink-0" aria-hidden="true" />
        )}
        <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
          {laneIcon(lane.categoryId !== null, 'h-4 w-4 shrink-0 text-primary')}
          <span className="min-w-0 break-words">{name}</span>
        </h3>
        <LaneOwner lane={lane} peers={peers} />
        <span
          className="shrink-0 text-xs text-muted-foreground"
          data-testid={`lane-count-${lane.key}`}
        >
          {t('workboard.board.column_count', { count })}
        </span>
        {onAdd && lane.mine && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            aria-label={t('workboard.lanes.add_ticket', { name })}
            onClick={() => onAdd(lane.categoryId)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </Button>
        )}
      </div>
    </header>
  );
}

interface LaneCellProps {
  lane: LaneView;
  laneName: string;
  status: string;
  tickets: readonly TicketRow[];
  /** The EXACT number of tickets in this cell, from the server. */
  exact: number;
  /** Whether the dragged card may land here. */
  open: boolean;
  draggable: boolean;
  /** Whether this cell opens a column that has another one before it. */
  ruled: boolean;
  cards: CardHandlers;
}

function LaneCell({
  lane,
  laneName,
  status,
  tickets,
  exact,
  open,
  draggable,
  ruled,
  cards,
}: LaneCellProps) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({
    id: cellDroppableId(lane.key, status),
    disabled: !open,
  });
  // The cards take the ground their lane does not: the two alternate.
  const ground = laneGround(lane.stripe) === 'card' ? 'background' : 'card';
  const elsewhere = Math.max(0, exact - tickets.length);
  const list = tickets.length > 0 && (
    <ul className="flex flex-col gap-2">
      {tickets.map(ticket =>
        draggable ? (
          <SortableCard key={ticket.id} ticket={ticket} ground={ground} closed={!open} {...cards} />
        ) : (
          <li key={ticket.id}>
            <TicketCard ticket={ticket} ground={ground} {...cards} />
          </li>
        )
      )}
    </ul>
  );
  return (
    <div
      ref={setNodeRef}
      role="group"
      aria-label={t('workboard.lanes.cell', {
        column: t(`workboard.columns.${status}`),
        lane: laneName,
      })}
      data-testid={`cell-${lane.key}-${status}`}
      className={cn(
        'relative min-h-16 rounded-lg p-1',
        isOver && 'bg-primary/5 ring-1 ring-primary/40'
      )}
    >
      {/* From the top of the cells to the lane's own bottom line. */}
      {ruled && <ColumnRule reach="top-0 -bottom-3" />}
      {draggable ? (
        <SortableContext items={tickets.map(row => row.id)} strategy={verticalListSortingStrategy}>
          {list}
        </SortableContext>
      ) : (
        list
      )}
      {elsewhere > 0 && (
        // The lane's header counts them; this page does not carry them. Saying
        // so is what keeps the header and the cell from disagreeing (ADR-185).
        <p className="px-1 pt-1 text-px-11 text-muted-foreground">
          {t('workboard.lanes.off_page', { count: elsewhere })}
        </p>
      )}
    </div>
  );
}

export interface LaneProps {
  lane: LaneView;
  /** The columns to draw a cell for: every column from `lg` up, one on a phone. */
  statuses: readonly string[];
  /** The cards of one cell of this lane, in the column's order. */
  cell: (status: string) => readonly TicketRow[];
  folded: boolean;
  /** Whether the dragged card may land in this lane — true while nothing drags. */
  open: boolean;
  draggable: boolean;
  /** The grid the cells share with the column headers above them. */
  template?: React.CSSProperties;
  /** Pin the header under the application header — the phone. */
  pinned?: boolean;
  onToggle: () => void;
  onAdd?: (categoryId: string | null) => void;
  cards: CardHandlers;
}

export function Lane({
  lane,
  statuses,
  cell,
  folded,
  open,
  draggable,
  template,
  pinned = false,
  onToggle,
  onAdd,
  cards,
}: LaneProps) {
  const { t } = useTranslation();
  const name = lane.name ?? t('workboard.lanes.unfiled');
  const cells = statuses.map(status => ({ status, tickets: cell(status) }));
  // What the header counts is what is drawn under it: every column from `lg`
  // up, the ONE column a phone shows below it — a header saying twelve above
  // a column holding two would be the disagreement ADR-185 forbids.
  const count = statuses.reduce((sum, status) => sum + (lane.countsByStatus[status] ?? 0), 0);
  // An empty lane is its header: a row of empty cells would be six boxes
  // saying nothing. « Empty » reads the server's count AND what is on screen,
  // so a card the count does not know yet is never hidden.
  const holds = count > 0 || cells.some(entry => entry.tickets.length > 0);
  return (
    <section
      aria-label={t('workboard.lanes.label', { name })}
      data-testid={`lane-${lane.key}`}
      data-lane-ground={laneGround(lane.stripe)}
      className={cn(
        'border-b border-border last:border-b-0',
        laneGround(lane.stripe) === 'card' ? 'bg-card' : 'bg-background',
        // Closed to the card in the air: dimmed, and none of its targets take it.
        !open && 'opacity-50'
      )}
    >
      <LaneHeader
        lane={lane}
        name={name}
        count={count}
        peers={cards.peers}
        foldable={holds}
        folded={folded}
        open={open}
        pinned={pinned}
        onToggle={onToggle}
        onAdd={onAdd}
      />
      {holds && !folded && (
        <div id={bodyId(lane)} className="grid gap-3 px-3 pb-3" style={template}>
          {cells.map((entry, index) => (
            <LaneCell
              key={entry.status}
              lane={lane}
              laneName={name}
              status={entry.status}
              tickets={entry.tickets}
              exact={lane.countsByStatus[entry.status] ?? 0}
              open={open}
              draggable={draggable}
              // Every column that follows another one — so none where a
              // phone draws a single column.
              ruled={index > 0}
              cards={cards}
            />
          ))}
        </div>
      )}
    </section>
  );
}
