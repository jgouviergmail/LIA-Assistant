'use client';

/**
 * One sortable column header of the administrators' user table.
 *
 * The headers used to be `<th onClick>`: sortable with a mouse, not with a
 * keyboard, and written out twenty-seven times. The sort control is now a
 * native button inside the header cell — focusable, activated by Enter and
 * Space — while `aria-sort` stays on the `columnheader`, where assistive
 * technology reads it. An icon header carries its name in `sr-only` text (the
 * `title` tooltip is for the pointer only; it does not exist on a touch screen,
 * which is what the table's legend is for).
 */

import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

export type SortOrder = 'asc' | 'desc';

export interface SortableHeaderProps<Column extends string> {
  column: Column;
  /** Already translated: the visible text, or the icon's accessible name. */
  label: string;
  /** Renders the icon instead of the text; the label then names it. */
  icon?: LucideIcon;
  /** Pointer tooltip, when the visible text is an abbreviation. */
  title?: string;
  align?: 'left' | 'center' | 'right';
  sortBy: Column;
  sortOrder: SortOrder;
  onSort: (column: Column) => void;
  /** Extra classes for the cell (the frozen columns' position). */
  className?: string;
}

/** Alignment, and the padding of the cells below it. */
const ALIGN = {
  left: 'justify-start px-4 text-left',
  center: 'justify-center px-3 text-center',
  right: 'justify-end px-3 text-right',
} as const;

export function SortableHeader<Column extends string>({
  column,
  label,
  icon: Icon,
  title,
  align = 'left',
  sortBy,
  sortOrder,
  onSort,
  className,
}: SortableHeaderProps<Column>) {
  const active = sortBy === column;
  let ariaSort: 'ascending' | 'descending' | 'none' = 'none';
  if (active) ariaSort = sortOrder === 'asc' ? 'ascending' : 'descending';
  const arrow = sortOrder === 'asc' ? '↑' : '↓';
  return (
    <th scope="col" aria-sort={ariaSort} className={cn('p-0', className)}>
      <button
        type="button"
        onClick={() => onSort(column)}
        title={title ?? (Icon ? label : undefined)}
        className={cn(
          'flex w-full items-center gap-0.5 whitespace-nowrap py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
          ALIGN[align]
        )}
      >
        {Icon ? (
          <>
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{label}</span>
          </>
        ) : (
          <span>{label}</span>
        )}
        {active && <span aria-hidden="true">{arrow}</span>}
      </button>
    </th>
  );
}
