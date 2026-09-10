'use client';
/**
 * The seven columns, and the two ways to move a card between them (ADR-276).
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
 * there: a finger that presses a card opens its detail, and the two lists on
 * the card — or the panel's — are where a phone changes the column or the
 * holder. A swipe is a travel of
 * at least `SWIPE_MIN_PX` that is clearly more sideways than down — anything
 * else is the scroll it looks like.
 *
 * The `DndContext` wraps BOTH layouts: the sensors decide what a gesture means,
 * never a second copy of the rule sitting outside them.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCorners,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Column, type ColumnProps } from '@/components/workboard/Column';
import { StatusSelect } from '@/components/workboard/StatusSelect';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { columnOfDroppable, dragSpeech, resolveDrop, titleOf } from '@/lib/workboard/dnd';
import { CONDITIONAL_STATUSES, TICKET_STATUSES, type TicketRow } from '@/types/workboard';

type CardHandlers = Omit<ColumnProps, 'status' | 'tickets' | 'count' | 'draggable' | 'className'>;

/** A horizontal travel below this is a scroll, not a swipe. */
export const SWIPE_MIN_PX = 48;

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
  onMove: (id: string, status: string, position: number) => void;
}

export function Board({ column, countsByStatus, onMove, onDragActive, ...cards }: BoardProps) {
  const { t } = useTranslation();
  const wide = useMediaQuery('(min-width: 1024px)');
  const [dragged, setDragged] = useState<TicketRow | null>(null);
  const [shown, setShown] = useState<string>('todo');
  // A conditional column is drawn only while it holds a ticket: « À
  // confirmer » would otherwise be an empty eighth column on every board.
  const shownStatuses = TICKET_STATUSES.filter(
    status => !CONDITIONAL_STATUSES.has(status) || (countsByStatus[status] ?? 0) > 0
  );
  // The shown column is DERIVED, never trusted: « À confirmer » comes and goes
  // with the ticket it holds, so a reader watching it while they answer would
  // be left on a column the board no longer draws — an empty region, a list
  // with no selected value and a dead « previous » arrow. Derived rather than
  // corrected in an effect: a `setState` during a render is the ratchet's own
  // refusal, and there is nothing to store that the columns do not already say.
  const current = shownStatuses.includes(shown as (typeof TICKET_STATUSES)[number])
    ? shown
    : (shownStatuses[0] ?? TICKET_STATUSES[0]);
  const shownIndex = shownStatuses.indexOf(current as (typeof TICKET_STATUSES)[number]);
  // ONE way to step through the columns for the arrows and the swipe alike,
  // over the columns actually DRAWN: stepping through `TICKET_STATUSES` landed
  // on « à confirmer » while it was hidden.
  const step = (delta: number) => {
    const index = Math.min(shownStatuses.length - 1, Math.max(0, shownIndex + delta));
    setShown(shownStatuses[index]);
  };
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const onTouchStart = (event: React.TouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0];
    touchStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
  };
  const onTouchEnd = (event: React.TouchEvent<HTMLDivElement>) => {
    const start = touchStart.current;
    touchStart.current = null;
    const touch = event.changedTouches[0];
    if (!start || !touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy) * 2) return;
    step(dx < 0 ? 1 : -1);
  };

  const statusOf = useCallback(
    (id: string) => {
      for (const status of TICKET_STATUSES) {
        if (column(status).some(row => row.id === id)) return status;
      }
      return null;
    },
    [column]
  );

  const sensors = useSensors(
    useSensor(PointerSensor, {
      // A few pixels of travel before a drag begins: without it, every click on
      // a card's title is read as the start of one.
      activationConstraint: { distance: 8 },
    }),
    useSensor(TouchSensor, {
      // Press and hold. A finger scrolling the column must never pick a card up
      // — the defect that makes a touch board unusable.
      activationConstraint: { delay: 250, tolerance: 8 },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
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
    <div className="space-y-3" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          aria-label={t('workboard.board.previous_column')}
          disabled={shownIndex <= 0}
          onClick={() => step(-1)}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        {/* The SAME list a card carries, with the exact count beside each
            column: choosing one is an informed pick. */}
        <StatusSelect
          label={t('workboard.board.pick_column')}
          value={current}
          statuses={shownStatuses}
          counts={countsByStatus}
          className="h-10 flex-1 px-3 text-sm"
          onChange={setShown}
        />
        <Button
          variant="outline"
          size="icon"
          aria-label={t('workboard.board.next_column')}
          disabled={shownIndex >= shownStatuses.length - 1}
          onClick={() => step(1)}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      {columnFor(current)}
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
