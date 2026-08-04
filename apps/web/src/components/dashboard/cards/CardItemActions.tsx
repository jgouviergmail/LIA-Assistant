'use client';

/**
 * CardItemActions — the per-item actions of a briefing card, behind ONE
 * trigger.
 *
 * QW-9 made every briefing item a button that PREFILLS the chat. QW-24 added
 * named actions that EXECUTE: each one deep-links to `?intent=`, which the chat
 * auto-sends through the normal pipeline (ADR-173) — so external writes keep
 * their tool-level HITL cards, and nothing bypasses approval.
 *
 * They used to render as a ROW of icon chips, and that row cost the item its
 * words. Each chip is 26 px (`p-1.5` around a 14 px icon) plus a 2 px gap, so
 * two or three of them — with the Drive link, four on documents — took 82 to
 * 110 px out of a row whose usable width is ~330 px in the 2-column grid and
 * ~365 px in the 3-column one. A quarter to a third of the line, spent on
 * icons, and the title `truncate`d to pay for it.
 *
 * One trigger reserves 26 px no matter how many actions there are. Every row of
 * every card therefore reserves the SAME width, which is what makes the text
 * column identical throughout — a chip for one action and a menu for three
 * would bring the variable width straight back (owner arbitration 2026-08-03).
 *
 * Rendered as a SIBLING of the item's main button, never inside it: nested
 * buttons are invalid HTML and unreachable by assistive technology.
 */

import { useCallback, useRef } from 'react';
import { MoreHorizontal, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export interface CardItemAction {
  icon: LucideIcon;
  /** Full localized sentence — it is also the item's accessible name. */
  label: string;
  /** What the choice does. Omitted for a pure navigation (`href`). */
  onSelect?: () => void;
  /**
   * External destination, rendered as a real anchor inside the menu.
   *
   * Navigation is not a click handler: an anchor gives the browser its
   * middle-click, its context menu and its status-bar preview. This replaces
   * the old `trailing` slot, which put a second visible affordance next to the
   * chips — exactly the extra width this component exists to remove.
   */
  href?: string;
  /**
   * A write is in flight for this item.
   *
   * `aria-disabled`, never `disabled`: the attribute on a FOCUSED control blurs
   * it and drops it from the tab order, leaving a keyboard user on `<body>`.
   * The guard in the handler is what prevents the double submit — this only
   * says so.
   */
  busy?: boolean;
}

/** Shared chip classes — kept for callers that style a matching control. */
export const CARD_ITEM_ACTION_CLASS =
  'p-1.5 rounded-md text-muted-foreground/70 hover:text-primary hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors';

export interface CardItemActionsProps {
  actions: readonly CardItemAction[];
}

export function CardItemActions({ actions }: CardItemActionsProps) {
  const { t } = useTranslation();
  /**
   * Whether the menu is closing BECAUSE an action was chosen.
   *
   * Radix restores focus to its trigger on close. That trigger lives inside
   * the row, and several actions REMOVE the row (closing a commitment,
   * cancelling a reminder): the restore then lands on a detached node and the
   * keyboard user is dropped on `<body>`. It also fights the card's own
   * anchor, which takes focus deliberately — and does so AFTER awaiting the
   * write, so Radix's restore always came last and won.
   *
   * An action that ran therefore owns the focus: each one moves it (the card's
   * named region, an autofocused editor, an alert dialog, or a navigation
   * away). A dismissal without a choice keeps Radix's restore, which is
   * exactly right — the trigger is still there and it is where the reader was.
   */
  const chosen = useRef(false);

  const handleCloseAutoFocus = useCallback((event: Event) => {
    if (!chosen.current) return;
    chosen.current = false;
    event.preventDefault();
  }, []);

  if (actions.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('dashboard.briefing.actions.more')}
          className={cn(CARD_ITEM_ACTION_CLASS, 'shrink-0')}
        >
          <MoreHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      {/* `align="end"`: the trigger sits at the right edge of a narrow card, so
          a centred menu would overflow the grid column. */}
      <DropdownMenuContent
        align="end"
        className="max-w-[min(20rem,calc(100vw-2rem))]"
        onCloseAutoFocus={handleCloseAutoFocus}
      >
        {actions.map(action => (
          <DropdownMenuItem
            key={action.label}
            asChild={action.href !== undefined}
            aria-disabled={action.busy || undefined}
            // Radix would still fire `onSelect` on an `aria-disabled` item —
            // the attribute states the state, the guard enforces it.
            onSelect={
              action.busy
                ? undefined
                : () => {
                    chosen.current = true;
                    action.onSelect?.();
                  }
            }
            className={cn('gap-2', action.busy && 'opacity-50')}
          >
            {action.href !== undefined ? (
              <a
                href={action.href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex w-full cursor-pointer items-center gap-2"
              >
                <action.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{action.label}</span>
              </a>
            ) : (
              <>
                <action.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{action.label}</span>
              </>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
