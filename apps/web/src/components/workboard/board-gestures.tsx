'use client';
/**
 * What the two shapes of the board share (ADR-276).
 *
 * The board is drawn flat (seven columns) or in lanes (one row of columns per
 * category), and both obey the same gestures: the same sensors decide what a
 * press means, and below `lg` both show ONE column at a time, walked with two
 * arrows, a list or a horizontal swipe. Written once here so the two shapes
 * cannot drift apart — a swipe threshold tuned on one and forgotten on the
 * other is exactly the kind of difference nobody notices until a phone.
 */
import { useRef, useState } from 'react';
import {
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type SensorDescriptor,
  type SensorOptions,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { StatusSelect } from '@/components/workboard/StatusSelect';
import { ChevronLeft, ChevronRight } from '@/lib/icons';
import { CONDITIONAL_STATUSES, TICKET_STATUSES } from '@/types/workboard';

/** A horizontal travel below this is a scroll, not a swipe. */
export const SWIPE_MIN_PX = 48;

/**
 * The sensors of the board: pointer, touch and keyboard.
 *
 * The keyboard sensor is not an extra — keyboard equivalence is a correctness
 * rule in this repository.
 *
 * @returns The sensors to hand to `DndContext`.
 */
export function useBoardSensors(): SensorDescriptor<SensorOptions>[] {
  return useSensors(
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
}

/**
 * The columns the board draws.
 *
 * A conditional column is drawn only while it holds a ticket: « À confirmer »
 * would otherwise be an empty eighth column on every board.
 *
 * @param countsByStatus - The EXACT count per column, from the server.
 * @returns The columns, in board order.
 */
export function drawnStatuses(countsByStatus: Record<string, number>): readonly string[] {
  return TICKET_STATUSES.filter(
    status => !CONDITIONAL_STATUSES.has(status) || (countsByStatus[status] ?? 0) > 0
  );
}

/** The one column a phone shows, and the three ways to change it. */
export interface ShownColumn {
  /** The column on screen. */
  current: string;
  /** Its index among the columns drawn. */
  index: number;
  /** Step to a neighbour, stopping at both ends. */
  step: (delta: number) => void;
  /** Show a column picked from the list. */
  pick: (status: string) => void;
  /** Spread on the container the swipe is read from. */
  swipe: {
    onTouchStart: (event: React.TouchEvent<HTMLDivElement>) => void;
    onTouchEnd: (event: React.TouchEvent<HTMLDivElement>) => void;
  };
}

/**
 * Which column a phone shows.
 *
 * The shown column is DERIVED, never trusted: « À confirmer » comes and goes
 * with the ticket it holds, so a reader watching it while they answer would be
 * left on a column the board no longer draws — an empty region, a list with no
 * selected value and a dead « previous » arrow. Derived rather than corrected
 * in an effect: a `setState` during a render is the ratchet's own refusal, and
 * there is nothing to store that the columns do not already say.
 *
 * A swipe is a travel of at least `SWIPE_MIN_PX` that is clearly more sideways
 * than down — anything else is the scroll it looks like.
 *
 * @param statuses - The columns the board draws.
 * @returns The shown column and its controls.
 */
export function useShownColumn(statuses: readonly string[]): ShownColumn {
  const [shown, setShown] = useState<string>('todo');
  const current = statuses.includes(shown) ? shown : (statuses[0] ?? TICKET_STATUSES[0]);
  const index = statuses.indexOf(current);
  // ONE way to step through the columns for the arrows and the swipe alike,
  // over the columns actually DRAWN: stepping through `TICKET_STATUSES` landed
  // on « à confirmer » while it was hidden.
  const step = (delta: number) => {
    setShown(statuses[Math.min(statuses.length - 1, Math.max(0, index + delta))]);
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
  return { current, index, step, pick: setShown, swipe: { onTouchStart, onTouchEnd } };
}

/**
 * The phone's column bar: two arrows around the column list.
 *
 * The SAME list a card carries, with the exact count beside each column:
 * choosing one is an informed pick.
 */
export function ColumnPicker({
  column,
  statuses,
  counts,
}: {
  column: ShownColumn;
  statuses: readonly string[];
  counts: Record<string, number>;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="icon"
        aria-label={t('workboard.board.previous_column')}
        disabled={column.index <= 0}
        onClick={() => column.step(-1)}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </Button>
      <StatusSelect
        label={t('workboard.board.pick_column')}
        value={column.current}
        statuses={statuses}
        counts={counts}
        className="h-10 flex-1 px-3 text-sm"
        onChange={column.pick}
      />
      <Button
        variant="outline"
        size="icon"
        aria-label={t('workboard.board.next_column')}
        disabled={column.index >= statuses.length - 1}
        onClick={() => column.step(1)}
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  );
}
