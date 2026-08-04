'use client';

/**
 * CardItemRow — one line of a briefing card: the item, its label on hover, and
 * its actions behind a single trigger.
 *
 * Seven cards were writing the same `<li>` by hand — the flex row, the
 * full-width button with its hover tint and focus ring, the negative margin
 * that lets the hover surface bleed past the text, the action chips as
 * siblings. Seven copies is seven chances for one of them to drift, and the
 * bubble below would have had to be added seven times.
 *
 * **The bubble is not decoration.** The row's accessible name is the INTENT
 * sentence the click sends ("prepare me for X at 10:00"), never the raw title,
 * so the title was announced to nobody; and the visible text is `truncate`d or
 * `line-clamp`ed by design, so a sighted reader could not read it either.
 * Radix's tooltip opens on hover AND on keyboard focus, and wires itself as
 * `aria-describedby`, so the item's own words become reachable by both routes.
 * It portals to the body, so the card's `overflow-y-auto` never clips it.
 */

import type { ReactNode } from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { CardItemActions, type CardItemAction } from './CardItemActions';

export interface CardItemRowProps {
  /** What the CLICK does — the row's accessible name. */
  ariaLabel: string;
  /**
   * The item's own words, shown in the bubble.
   *
   * Always rendered, even when the text happens to fit: measuring truncation
   * per row would need a ResizeObserver on every line of every card, and a
   * bubble that appears only sometimes is a worse contract than one that
   * always does.
   */
  tooltip: string;
  onSelect: () => void;
  actions?: readonly CardItemAction[];
  /** `items-start` for multi-line items, `items-center` for single-line ones. */
  align?: 'start' | 'center';
  /** Layout of the button's own content — the card owns what it shows. */
  contentClassName?: string;
  children: ReactNode;
}

export function CardItemRow({
  ariaLabel,
  tooltip,
  onSelect,
  actions = [],
  align = 'start',
  contentClassName,
  children,
}: CardItemRowProps) {
  return (
    <li className={cn('flex gap-1', align === 'center' ? 'items-center' : 'items-start')}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onSelect}
            aria-label={ariaLabel}
            className={cn(
              'min-w-0 flex-1 rounded-md px-1.5 py-1 -mx-1.5 text-left',
              'hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              contentClassName
            )}
          >
            {children}
          </button>
        </TooltipTrigger>
        {/* `collisionPadding`: rows sit at the very edge of a grid column, and
            an unpadded bubble was clipped by the viewport on a phone. */}
        <TooltipContent
          side="top"
          collisionPadding={8}
          className="max-w-[min(22rem,calc(100vw-2rem))] whitespace-pre-line"
        >
          {tooltip}
        </TooltipContent>
      </Tooltip>
      <CardItemActions actions={actions} />
    </li>
  );
}
