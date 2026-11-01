'use client';

/**
 * EventChip — an event drawn in a view (ADR-369, mock-up « Agenda »).
 *
 * A link to the event (it rides the address, so « back » closes it), edged and
 * tinted with its calendar's colour — data the provider keeps, drawn as it is
 * (spec §7: the calendar colours are the one literal colour allowed) — or the
 * accent where the calendar has none. Its title and, when given, its times.
 */
import Link from 'next/link';
import type { CSSProperties } from 'react';

import { cn } from '@/lib/utils';

const HEX = /^#[0-9a-f]{6}$/i;

/** @returns The calendar's colour when it is one (#rrggbb); null for anything else. */
export function calendarColor(color: string | null): string | null {
  return color && HEX.test(color) ? color : null;
}

/** @returns The edge and tint of a calendar colour; none for an unreadable one. */
export function calendarTint(color: string | null): CSSProperties | undefined {
  const known = calendarColor(color);
  return known ? { borderLeftColor: known, backgroundColor: `${known}26` } : undefined;
}

/** A calendar's colour as a small square (the accent when it has none). */
export function CalendarSwatch({ color, className }: { color: string | null; className?: string }) {
  const known = calendarColor(color);
  return (
    <span
      aria-hidden="true"
      className={cn('shrink-0 rounded-sm', !known && 'bg-primary', className)}
      style={known ? { backgroundColor: known } : undefined}
    />
  );
}

export interface EventChipProps {
  href: string;
  summary: string;
  /** The words for an event with no title. */
  untitled: string;
  color: string | null;
  times?: string;
  /** The open event's chip. */
  current?: boolean;
  className?: string;
  style?: CSSProperties;
  /** Hands the link to the drill-down focus (`useDrillDownFocus`). */
  linkRef?: (element: HTMLAnchorElement | null) => void;
}

export function EventChip({
  href,
  summary,
  untitled,
  color,
  times,
  current,
  className,
  style,
  linkRef,
}: EventChipProps) {
  const tint = calendarTint(color);
  return (
    <Link
      ref={linkRef}
      href={href}
      scroll={false}
      aria-current={current ? 'true' : undefined}
      className={cn(
        'block min-w-0 overflow-hidden rounded-md border-l-[3px] px-1.5 py-0.5 text-xs leading-tight text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:ring-2 aria-[current=true]:ring-primary',
        !tint && 'border-l-primary bg-primary/10',
        className
      )}
      style={{ ...tint, ...style }}
    >
      <span className="block truncate font-semibold">{summary || untitled}</span>
      {/* The foreground, never the muted grey: on a calendar's tint the muted grey
          measured 4.27:1 (axe, week view); the weight alone tells it from the title. */}
      {times && <span className="block truncate">{times}</span>}
    </Link>
  );
}
