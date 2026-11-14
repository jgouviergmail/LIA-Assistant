'use client';
/**
 * The board in lanes: one row of the columns per category (ADR-276).
 *
 * The flat board reads ACROSS — seven columns. With categories it reads in two
 * directions, and each of them keeps one job: a COLUMN says where the work is,
 * a LANE says what it belongs to. The columns are named once, above the lanes;
 * every lane repeats them as cells.
 *
 * **From `lg` up** the board is its OWN scroll region, in both directions. A
 * lane board is taller than the screen as soon as three lanes hold work, and a
 * reader half-way down must still see which column is which: the column names
 * stick to the top of the region. A sticky row cannot stick to the page from
 * inside a sideways scroller — the scroller becomes its containing block — so
 * the region scrolls both ways and is bounded to the screen (measured in a
 * browser, 2026-11-11). The page body still never scrolls sideways.
 *
 * **Below `lg`** one column shows at a time, as on the flat board, and the
 * lanes are its groups: each lane's name stays pinned under the application
 * header while its cards scroll. Nothing drags there — the category is a list
 * on the card, beside the column and the holder.
 *
 * **The category is the OWNER's.** While a card is in the air, the lanes it
 * may not enter are closed: dimmed, their targets disabled. The drop is then
 * judged a second time by the same rule (`laneMove`) before anything is sent.
 */
import { useCallback, useMemo, useState } from 'react';
import {
  DndContext,
  closestCorners,
  pointerWithin,
  type Announcements,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { useTranslation } from 'react-i18next';

import type { BoardProps } from '@/components/workboard/Board';
import {
  ColumnPicker,
  drawnStatuses,
  useBoardSensors,
  useShownColumn,
} from '@/components/workboard/board-gestures';
import { liveness } from '@/components/workboard/Column';
import { ColumnRule, Lane } from '@/components/workboard/Lane';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { cn } from '@/lib/utils';
import { laneMove, laneSpeech, placeOf } from '@/lib/workboard/dnd';
import { columnIcon } from '@/lib/workboard/icons';
import {
  canFile,
  knownCategories,
  laneOf,
  ticketsOfCell,
  type LaneView,
} from '@/lib/workboard/lanes';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';
import type { TicketRow } from '@/types/workboard';

/**
 * The narrowest a column gets before the board scrolls sideways, in rem — the
 * flat board's own floor, so a board does not change its measure the day its
 * reader creates a category.
 */
const COLUMN_FLOOR_REM = 11;

/**
 * What the card in the air is over.
 *
 * Under a pointer it is what the pointer is IN: a lane's header is a strip the
 * whole width of the board, and « closest corners » never picks a strip that
 * long over the cards near it — an empty lane, which is its header alone,
 * would be a target nobody could hit. The keyboard has no pointer and steps
 * from one target's corner to the next, so it keeps the corners.
 */
const overWhat: CollisionDetection = args => {
  const inside = args.pointerCoordinates ? pointerWithin(args) : [];
  return inside.length > 0 ? inside : closestCorners(args);
};

export interface LaneBoardProps extends Omit<BoardProps, 'lanes' | 'narrowed'> {
  /** The lanes drawn, in order. */
  lanes: readonly LaneView[];
  /**
   * The key of EVERY lane of the board, drawn or not. A fold is remembered for
   * these: a lane a filter is hiding has not stopped existing.
   */
  laneKeys: readonly string[];
}

/** One column's name and exact count, above the lanes. */
function ColumnHeader({
  status,
  count,
  ruled,
}: {
  status: string;
  count: number;
  /** Whether this column has another one before it, to be marked off from. */
  ruled: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="relative flex min-w-0 items-center justify-between gap-2 px-1"
      data-testid={`column-header-${status}`}
    >
      {/* Through the row's own padding, from its top to the line under it. */}
      {ruled && <ColumnRule reach="-top-2 -bottom-2" />}
      <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
        {columnIcon(status, cn('h-4 w-4 shrink-0 text-primary', liveness(status, count)))}
        <span className="truncate">{t(`workboard.columns.${status}`)}</span>
      </h3>
      <span className="shrink-0 text-xs text-muted-foreground" data-testid={`count-${status}`}>
        {t('workboard.board.column_count', { count })}
      </span>
    </div>
  );
}

export function LaneBoard({
  lanes,
  laneKeys,
  column,
  countsByStatus,
  onMove,
  onDragActive,
  onAdd,
  ...cards
}: LaneBoardProps) {
  const { t } = useTranslation();
  const wide = useMediaQuery('(min-width: 1024px)');
  const [dragged, setDragged] = useState<TicketRow | null>(null);
  const statuses = drawnStatuses(countsByStatus);
  const shown = useShownColumn(statuses);
  const sensors = useBoardSensors();
  const collapsed = useWorkboardLanesStore(state => state.collapsed);
  const toggle = useWorkboardLanesStore(state => state.toggle);
  const known = useMemo(() => knownCategories(lanes), [lanes]);
  const { loaded, meId } = cards;

  const find = useCallback((id: string) => loaded.find(row => row.id === id) ?? null, [loaded]);

  const announcements: Announcements = useMemo(() => {
    const speech = laneSpeech(t);
    const laneName = (categoryId: string | null) =>
      lanes.find(lane => lane.categoryId === categoryId)?.name ?? t('workboard.lanes.unfiled');
    // A background refresh is held while a card is in the air, but the row is
    // read from the page first and from the gesture's own memory second: an
    // announcement about nothing is worse than one about what was picked up.
    const moving = (id: string) => find(id) ?? dragged;
    const title = (id: string) => moving(id)?.title ?? id;
    const where = (activeId: string, overId: string | undefined) => {
      const row = moving(activeId);
      const place = overId && row ? placeOf(overId, find, known, row.status) : null;
      return place
        ? { column: t(`workboard.columns.${place.status}`), lane: laneName(place.lane) }
        : null;
    };
    return {
      onDragStart: ({ active }) => {
        const id = String(active.id);
        const place = where(id, id);
        return speech.pickedUp(title(id), place?.column ?? '', place?.lane ?? '');
      },
      onDragOver: ({ active, over }) => {
        const place = where(String(active.id), over ? String(over.id) : undefined);
        return place ? speech.movedOver(title(String(active.id)), place.column, place.lane) : '';
      },
      onDragEnd: ({ active, over }) => {
        const id = String(active.id);
        const place = where(id, over ? String(over.id) : undefined);
        // Released over nothing: it went nowhere, and that is what is said.
        return place
          ? speech.dropped(title(id), place.column, place.lane)
          : speech.cancelled(title(id));
      },
      onDragCancel: ({ active }) => speech.cancelled(title(String(active.id))),
    };
  }, [dragged, find, known, lanes, t]);

  const onDragStart = useCallback(
    (event: DragStartEvent) => {
      setDragged(find(String(event.active.id)));
      // The board re-reads itself in the background; a payload landing while a
      // card is in the air would move the ground under the pointer.
      onDragActive?.(true);
    },
    [find, onDragActive]
  );

  const onDragEnd = useCallback(
    (event: DragEndEvent) => {
      setDragged(null);
      onDragActive?.(false);
      const id = String(event.active.id);
      const target = laneMove(
        id,
        event.over ? String(event.over.id) : null,
        column,
        find,
        lanes,
        meId
      );
      if (target) onMove(id, target.status, target.position, target.lane);
    },
    [column, find, lanes, meId, onDragActive, onMove]
  );

  const onDragCancel = useCallback(() => {
    setDragged(null);
    onDragActive?.(false);
  }, [onDragActive]);

  // The lanes the card in the air may enter. With nothing in the air, all of
  // them: a lane is closed for a card, never for the reader.
  const from = dragged ? laneOf(dragged, known) : null;
  const owns = dragged !== null && dragged.owner_user_id === meId;
  const isOpen = (lane: LaneView) => dragged === null || canFile(from, owns, lane);

  // Header and lanes share ONE grid, so a column is the same width in every
  // lane. The floor is the wrapper's: below it the region scrolls sideways and
  // the columns keep equal shares of what is left.
  const template = { gridTemplateColumns: `repeat(${statuses.length}, minmax(0, 1fr))` };
  const floor = {
    minWidth: `calc(${statuses.length} * ${COLUMN_FLOOR_REM}rem + ${statuses.length - 1} * 0.75rem + 1.5rem)`,
  };

  const laneFor = (lane: LaneView, shownStatuses: readonly string[], phone: boolean) => (
    <Lane
      key={lane.key}
      lane={lane}
      statuses={shownStatuses}
      cell={status => ticketsOfCell(column(status), lane.categoryId, known)}
      folded={collapsed.includes(lane.key)}
      open={isOpen(lane)}
      // Nothing drags below `lg`: a finger on a card opens it.
      draggable={!phone}
      template={phone ? undefined : template}
      pinned={phone}
      onToggle={() => toggle(lane.key, laneKeys)}
      onAdd={onAdd}
      cards={cards}
    />
  );

  const body = !wide ? (
    <div className="space-y-3" {...shown.swipe}>
      <ColumnPicker column={shown} statuses={statuses} counts={countsByStatus} />
      {/* `clip`, never `hidden`: `hidden` would make this box the containing
          block of the pinned lane names, and they would stop following the
          page. */}
      <div
        role="group"
        aria-label={t('workboard.lanes.board_label')}
        className="overflow-clip rounded-xl border border-border"
      >
        {lanes.map(lane => laneFor(lane, [shown.current], true))}
      </div>
    </div>
  ) : (
    <div
      role="group"
      aria-label={t('workboard.lanes.board_label')}
      data-testid="lane-board"
      // ONE scroll region, both ways, bounded to the screen under the
      // application header: what lets the column names stick.
      className="max-h-[calc(100dvh-5rem)] overflow-auto rounded-xl border border-border"
    >
      <div style={floor}>
        <div
          // On the page's ground: the first lane is on the card's, and the
          // alternation starts here.
          className="sticky top-0 z-20 grid gap-3 border-b border-border bg-background px-3 py-2"
          style={template}
        >
          {statuses.map((status, index) => (
            <ColumnHeader
              key={status}
              status={status}
              count={countsByStatus[status] ?? 0}
              ruled={index > 0}
            />
          ))}
        </div>
        {lanes.map(lane => laneFor(lane, statuses, false))}
      </div>
    </div>
  );

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={overWhat}
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
