'use client';

/**
 * EventChip — an event drawn in a view (ADR-369, mock-up « Agenda »).
 *
 * A link to the event (it rides the address, so « back » closes it), edged and
 * tinted with its calendar's colour — data the provider keeps, drawn as it is
 * (spec §7: the calendar colours are the one literal colour allowed) — or the
 * accent where the calendar has none. Its title and, when given, its times; a
 * small mark and words for a series; its call a link of its own beside the
 * event's, never inside it (a link holds no link). The frame around them takes
 * the place the view gives, and the drag where the view allows one.
 */
import { Repeat, Video } from '@/lib/icons';
import Link from 'next/link';
import type { CSSProperties, HTMLAttributes } from 'react';

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
  /** The bar of a month: no room above or below its line. */
  dense?: boolean;
  /** The words saying it belongs to a series; left out for a lone event. */
  seriesLabel?: string;
  /** Its call, where the chip has room for one. */
  join?: { href: string; label: string };
  /** dnd-kit's way in: the frame moves the event, its bottom edge stretches it. */
  setFrame?: (element: HTMLElement | null) => void;
  frameListeners?: HTMLAttributes<HTMLElement>;
  setEdge?: (element: HTMLElement | null) => void;
  edgeListeners?: HTMLAttributes<HTMLElement>;
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
  dense,
  seriesLabel,
  join,
  setFrame,
  frameListeners,
  setEdge,
  edgeListeners,
  className,
  style,
  linkRef,
}: EventChipProps) {
  const tint = calendarTint(color);
  return (
    <div
      ref={setFrame}
      {...frameListeners}
      className={cn('relative min-w-0', className)}
      style={style}
    >
      <Link
        ref={linkRef}
        href={href}
        scroll={false}
        draggable={false}
        aria-current={current ? 'true' : undefined}
        className={cn(
          'block h-full min-w-0 overflow-hidden rounded-md border-l-[3px] px-1.5 text-xs leading-tight text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-[current=true]:ring-2 aria-[current=true]:ring-primary',
          dense ? 'py-0' : 'py-0.5',
          join && 'pr-6',
          !tint && 'border-l-primary bg-primary/10'
        )}
        style={tint}
      >
        <span className="flex min-w-0 items-center gap-1">
          {seriesLabel && (
            <>
              <Repeat className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span className="sr-only">{seriesLabel}</span>
            </>
          )}
          <span className="truncate font-semibold">{summary || untitled}</span>
        </span>
        {/* The foreground, never the muted grey: on a calendar's tint the muted grey
            measured 4.27:1 (axe, week view); the weight alone tells it from the title. */}
        {times && <span className="block truncate">{times}</span>}
      </Link>
      {join && (
        <a
          href={join.href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={join.label}
          className="absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center rounded text-foreground hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Video className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
      {setEdge && (
        <span
          ref={setEdge}
          {...edgeListeners}
          aria-hidden="true"
          data-chip-resize=""
          className="absolute inset-x-0 bottom-0 h-1.5 cursor-ns-resize"
        />
      )}
    </div>
  );
}
