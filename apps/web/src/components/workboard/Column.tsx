'use client';
/**
 * One column of the board (ADR-276).
 *
 * The header states the EXACT number of tickets in that column — the server's
 * aggregate over the same filter, never the length of what this page happens to
 * carry (ADR-185): a board bigger than one page would otherwise under-report
 * every column at once.
 *
 * The column itself is a droppable so a card can be released on its empty
 * space; each card is sortable inside it — the WHOLE card, so a finger has
 * something to grab. Below `lg` one column shows at a time and a drag can only
 * reorder it; the touch sensor holds for 250 ms first, so scrolling a list
 * never picks a card up.
 */
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useTranslation } from 'react-i18next';

import { TicketCard, type TicketCardProps } from '@/components/workboard/TicketCard';
import { columnDroppableId } from '@/lib/workboard/dnd';
import { columnIcon } from '@/lib/workboard/icons';
import { cn } from '@/lib/utils';
import type { TicketRow } from '@/types/workboard';

type CardHandlers = Pick<
  TicketCardProps,
  | 'loaded'
  | 'total'
  | 'meId'
  | 'peers'
  | 'lng'
  | 'onOpen'
  | 'onFollowChange'
  | 'onDelete'
  | 'onStatusChange'
  | 'onAssigneeChange'
>;

export interface ColumnProps extends CardHandlers {
  status: string;
  tickets: readonly TicketRow[];
  /** The EXACT count for this column, from the server's aggregate. */
  count: number;
  /** Whether the cards can be picked up at all. */
  draggable: boolean;
  className?: string;
}

/** A card that can be picked up, dragged and dropped by pointer or keyboard. */
function SortableCard({ ticket, ...rest }: { ticket: TicketRow } & CardHandlers) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: ticket.id,
  });
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(isDragging && 'opacity-50')}
    >
      <TicketCard ticket={ticket} dragHandle={{ ...attributes, ...listeners }} {...rest} />
    </li>
  );
}

/**
 * How a column's glyph moves while it holds something.
 *
 * An empty column is still: motion is the signal, so it must mean « there is
 * something here » rather than decorate the header. « En cours » spins, because
 * its glyph IS a spinner and that is the one column where work is happening as
 * you look at it; the others breathe. Both are slowed well past Tailwind's
 * defaults — a board of six headers pulsing at 2 s reads as an alarm — and both
 * are `motion-safe`, so a reader who asked for stillness gets it.
 *
 * @param status - The column.
 * @param count - How many tickets it holds, from the server's aggregate.
 * @returns The classes to add to the glyph, or an empty string.
 */
function liveness(status: string, count: number): string {
  if (count <= 0) return '';
  return status === 'in_progress'
    ? 'motion-safe:animate-spin [animation-duration:3s]'
    : 'motion-safe:animate-pulse [animation-duration:2.6s]';
}

export function Column({ status, tickets, count, draggable, className, ...cards }: ColumnProps) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: columnDroppableId(status) });
  const ids = tickets.map(row => row.id);

  const list = (
    <ul className="flex flex-col gap-2" data-testid={`column-${status}`}>
      {tickets.map(ticket =>
        draggable ? (
          <SortableCard key={ticket.id} ticket={ticket} {...cards} />
        ) : (
          <li key={ticket.id}>
            <TicketCard ticket={ticket} {...cards} />
          </li>
        )
      )}
    </ul>
  );

  return (
    <section
      ref={setNodeRef}
      aria-label={t(`workboard.columns.${status}`)}
      className={cn(
        'flex min-h-32 flex-col gap-3 rounded-xl border border-border/50 bg-muted/30 p-3',
        isOver && 'border-primary/50 bg-primary/5',
        className
      )}
    >
      <header className="flex items-center justify-between gap-2">
        {/* A title always carries an icon, in the theme colour — the board is
            scanned column by column before it is read. */}
        <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold">
          {columnIcon(status, cn('h-4 w-4 shrink-0 text-primary', liveness(status, count)))}
          <span className="truncate">{t(`workboard.columns.${status}`)}</span>
        </h3>
        <span className="shrink-0 text-xs text-muted-foreground" data-testid={`count-${status}`}>
          {t('workboard.board.column_count', { count })}
        </span>
      </header>
      {tickets.length === 0 ? (
        // « Rien ici » is a claim, and the count beside it is the authority
        // (ADR-185): a board is paged at 200 rows where an account may own
        // 2 000, so a column can legitimately hold tickets that this page
        // does not carry. Saying it is empty there contradicts its own
        // header; saying they are elsewhere is what sends the reader to the
        // filters.
        <p className="py-4 text-center text-xs text-muted-foreground">
          {t(count > 0 ? 'workboard.empty.column_off_page' : 'workboard.empty.column')}
        </p>
      ) : draggable ? (
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {list}
        </SortableContext>
      ) : (
        list
      )}
    </section>
  );
}
