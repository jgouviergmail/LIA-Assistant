'use client';
/**
 * The board, in the shape its reader's categories give it (ADR-276).
 *
 * **With no category in sight** it is the flat board: the seven columns, and
 * the two ways to move a card between them. **With at least one lane** it is
 * the lane board (`LaneBoard`): one row of the same columns per category. The
 * choice is made here, once, from the lanes the SERVER sent — an empty list is
 * what a reader who never created a category receives, and they keep exactly
 * the board they had.
 *
 * What follows describes the flat board; the lane board states its own rules.
 *
 * **From `lg` up**: the columns sit side by side inside ONE horizontally
 * scrolling container, so the page body never scrolls sideways, and a card can
 * be dragged with the pointer OR with the keyboard — dnd-kit's keyboard sensor
 * is not an extra, it is the equivalence rule this repository treats as
 * correctness. Every step of a drag is ANNOUNCED from the locale, naming the
 * COLUMN rather than an index: « moved to position 3 » tells a screen-reader
 * user nothing about where their ticket went. The columns SHARE the width and
 * only scroll once they cannot: a fixed 288 px each showed five of seven on a
 * laptop and made the board a sideways hunt.
 *
 * **Below `lg`**: one column at a time, chosen with the column list the cards
 * carry (its items wear the column glyphs, lot 20), two arrows, or a
 * horizontal SWIPE across the column (owner, 2026-09-10). Nothing drags
 * there: a finger that presses a card opens its detail, and the lists on the
 * card — or the panel's — are where a phone changes the column or the holder.
 *
 * The `DndContext` wraps BOTH layouts: the sensors decide what a gesture means,
 * never a second copy of the rule sitting outside them. Those sensors, the
 * shown column and the swipe are shared with the lane board
 * (`board-gestures.tsx`).
 */
import { useCallback, useMemo, useState } from 'react';
import {
  DndContext,
  closestCorners,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { useTranslation } from 'react-i18next';

import {
  ColumnPicker,
  drawnStatuses,
  useBoardSensors,
  useShownColumn,
} from '@/components/workboard/board-gestures';
import { Column, type ColumnProps } from '@/components/workboard/Column';
import { LaneBoard } from '@/components/workboard/LaneBoard';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { columnOfDroppable, dragSpeech, resolveDrop, titleOf } from '@/lib/workboard/dnd';
import { laneKey, laneViews } from '@/lib/workboard/lanes';
import { TICKET_STATUSES, type LaneRow, type TicketRow } from '@/types/workboard';

export { SWIPE_MIN_PX } from '@/components/workboard/board-gestures';

type CardHandlers = Omit<ColumnProps, 'status' | 'tickets' | 'count' | 'draggable' | 'className'>;

export interface BoardProps extends CardHandlers {
  /** The cards of one column, in board order. */
  column: (status: string) => readonly TicketRow[];
  /** The EXACT count per column, from the server's aggregate. */
  countsByStatus: Record<string, number>;
  /**
   * Told whenever a card is picked up or put down, so the page can hold the
   * background refresh while the gesture lasts.
   */
  onDragActive?: (active: boolean) => void;
  /**
   * The drop. `lane` is the category the card lands in (`null` for the unfiled
   * lane) and is ABSENT when the drop names no lane — the flat board never
   * names one, and a move inside a lane does not either.
   */
  onMove: (id: string, status: string, position: number, lane?: string | null) => void;
  /** The board's lanes, as the server sent them; empty draws the flat board. */
  lanes?: readonly LaneRow[];
  /** Whether a filter narrows the board: an emptied lane is then not drawn. */
  narrowed?: boolean;
  /** Create a ticket straight into a lane (`null` for the unfiled one). */
  onAdd?: (categoryId: string | null) => void;
}

export function Board({ lanes, narrowed = false, onAdd, ...board }: BoardProps) {
  const views = useMemo(
    () => laneViews(lanes ?? [], board.meId, narrowed),
    [lanes, board.meId, narrowed]
  );
  // Every lane the server sent, drawn or not: a fold is remembered for a lane
  // a filter is hiding too.
  const laneKeys = useMemo(() => (lanes ?? []).map(lane => laneKey(lane.category_id)), [lanes]);
  if (views.length === 0) return <FlatBoard {...board} />;
  return <LaneBoard {...board} lanes={views} laneKeys={laneKeys} onAdd={onAdd} />;
}

type FlatBoardProps = Omit<BoardProps, 'lanes' | 'narrowed' | 'onAdd'>;

function FlatBoard({ column, countsByStatus, onMove, onDragActive, ...cards }: FlatBoardProps) {
  const { t } = useTranslation();
  const wide = useMediaQuery('(min-width: 1024px)');
  const [dragged, setDragged] = useState<TicketRow | null>(null);
  const shownStatuses = drawnStatuses(countsByStatus);
  const shown = useShownColumn(shownStatuses);
  const sensors = useBoardSensors();

  const statusOf = useCallback(
    (id: string) => {
      for (const status of TICKET_STATUSES) {
        if (column(status).some(row => row.id === id)) return status;
      }
      return null;
    },
    [column]
  );

  const columnName = useCallback(
    (id: string | undefined) => {
      if (!id) return '';
      const status = columnOfDroppable(id) ?? statusOf(id);
      return status ? t(`workboard.columns.${status}`) : '';
    },
    [statusOf, t]
  );

  const announcements: Announcements = useMemo(() => {
    const speech = dragSpeech(t);
    const named = (id: string) => dragged?.title ?? titleOf(id, cards.loaded);
    return {
      onDragStart: ({ active }) =>
        speech.pickedUp(named(String(active.id)), columnName(String(active.id))),
      onDragOver: ({ active, over }) =>
        speech.movedOver(named(String(active.id)), columnName(over ? String(over.id) : undefined)),
      onDragEnd: ({ active, over }) =>
        speech.dropped(named(String(active.id)), columnName(over ? String(over.id) : undefined)),
      onDragCancel: ({ active }) => speech.cancelled(named(String(active.id))),
    };
  }, [cards.loaded, columnName, dragged, t]);

  const onDragStart = useCallback(
    (event: DragStartEvent) => {
      const id = String(event.active.id);
      setDragged(column(statusOf(id) ?? '').find(row => row.id === id) ?? null);
      // The board re-reads itself in the background; a payload landing while a
      // card is in the air would move the ground under the pointer.
      onDragActive?.(true);
    },
    [column, onDragActive, statusOf]
  );

  const onDragEnd = useCallback(
    (event: DragEndEvent) => {
      setDragged(null);
      onDragActive?.(false);
      const target = resolveDrop(
        String(event.active.id),
        event.over ? String(event.over.id) : null,
        column,
        statusOf
      );
      if (target) onMove(String(event.active.id), target.status, target.position);
    },
    [column, onDragActive, onMove, statusOf]
  );

  const onDragCancel = useCallback(() => {
    setDragged(null);
    onDragActive?.(false);
  }, [onDragActive]);

  const columnFor = (status: string) => (
    <Column
      key={status}
      status={status}
      tickets={column(status)}
      count={countsByStatus[status] ?? 0}
      // Nothing drags below `lg`: one column shows at a time, and a finger on
      // a card opens it instead.
      draggable={wide}
      // `flex-1` over a floor, never a fixed width: the columns share what the
      // screen gives and only scroll below the floor. The floor came down from
      // 208 px once the grip left the card — six columns at 176 px plus their
      // gaps fit a 1280 viewport, which is the point: a board is read ACROSS.
      className={wide ? 'w-44 min-w-44 flex-1' : ''}
      {...cards}
    />
  );

  const body = !wide ? (
    <div className="space-y-3" {...shown.swipe}>
      <ColumnPicker column={shown} statuses={shownStatuses} counts={countsByStatus} />
      {columnFor(shown.current)}
    </div>
  ) : (
    /* ONE horizontal scroller: the page body never scrolls sideways. */
    <div
      className="flex gap-3 overflow-x-auto pb-2"
      role="group"
      aria-label={t('workboard.board.label')}
    >
      {shownStatuses.map(columnFor)}
    </div>
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
      accessibility={{
        announcements,
        screenReaderInstructions: { draggable: t('workboard.dnd.instructions') },
      }}
    >
      {body}
    </DndContext>
  );
}
