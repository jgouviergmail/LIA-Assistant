'use client';

/**
 * The way out of a page, on a phone (A2).
 *
 * Below `lg` (raised from `md` by R01: five destinations clip in fr/de/es/it
 * between 768 and 1024 px) the header's `<nav>` is hidden and nothing once
 * replaced it: from the chat, a phone user could reach the dashboard through
 * the logo and NOTHING else — settings and help were unreachable without
 * typing a URL. The logo was already the only interactive landmark up there,
 * so it becomes the entry point rather than adding a burger that would cost
 * width the header does not have (measured: the trailing controls already
 * clip below 380 px).
 *
 * The logo therefore has two forms, mounted exclusively:
 *  - a LINK on `lg` and up, where the nav is visible — a menu would duplicate
 *    it and steal the plain "go home" gesture;
 *  - a BUTTON below `lg`, opening this menu, whose first item is that same
 *    "go home" destination so nothing is lost.
 *
 * Two elements rather than one element changing role: an element that is a link
 * at one width and a button at another cannot state its role to assistive
 * technology, and would hydrate differently from what the server rendered.
 *
 * ADR-259: the menu may carry ONE action after the destinations — on a phone
 * the header has no width for a seventh control (measured: 26 px over at
 * 390 px), so « Record a meeting » / « Stop the recording » lives here, and the
 * trigger itself pulses red while a recording is live (`live`).
 */

import Link from 'next/link';
import type { LucideIcon } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  DASHBOARD_DESTINATIONS,
  destinationPath,
  type DashboardDestination,
} from '@/lib/dashboard-nav';
import { cn } from '@/lib/utils';

/** One action the menu offers after the destinations (already translated). */
export interface MobileNavAction {
  label: string;
  icon: LucideIcon;
  /** `destructive` carries red at rest — Stop, never Record. */
  tone?: 'default' | 'destructive';
  disabled?: boolean;
  onSelect: () => void;
}

export interface MobileNavMenuProps {
  /** Builds the localized href of a route (the layout's own builder). */
  buildHref: (route: string) => string;
  /** Translates a label key (the layout's `t`). */
  translate: (key: string) => string;
  /** The layout's active-route predicate — single source of truth (no copy). */
  isActiveRoute: (segment: string) => boolean;
  /** Accessible name of the trigger, e.g. "Menu". */
  triggerLabel: string;
  /**
   * The destinations this instance offers (`visibleDestinations`); defaults
   * to the whole table. The layout passes the same list to the desktop nav.
   */
  destinations?: readonly DashboardDestination[];
  /** An action rendered after the destinations, behind a separator. */
  action?: MobileNavAction;
  /**
   * A live state the trigger must show: red, pulsing, and NAMED after the
   * state (`label` replaces `triggerLabel`) so a screen reader hears it too.
   */
  live?: { label: string };
}

export function MobileNavMenu({
  buildHref,
  translate,
  isActiveRoute,
  triggerLabel,
  destinations = DASHBOARD_DESTINATIONS,
  action,
  live,
}: MobileNavMenuProps) {
  const ActionIcon = action?.icon;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={live ? live.label : triggerLabel}
          // `h-11` (44 px), not the desktop logo's `h-10`: this is now a
          // CONTROL, and 40 px fails the touch-target floor the header
          // reachability spec enforces — it caught exactly that. The two forms
          // never show together, so the 4 px difference is invisible.
          className={cn(
            'flex h-11 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br shadow-md transition-all hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            live ? 'from-destructive to-destructive/80 animate-pulse' : 'from-primary to-primary/80'
          )}
        >
          <span
            className={cn(
              'text-sm font-bold',
              live ? 'text-destructive-foreground' : 'text-primary-foreground'
            )}
          >
            LIA
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        {destinations.map(({ segment, labelKey }) => (
          <DropdownMenuItem key={segment || 'home'} asChild>
            <Link
              href={buildHref(destinationPath(segment))}
              // `aria-current` states the active page; the tint alone would
              // convey it to sighted users only.
              aria-current={isActiveRoute(segment) ? 'page' : undefined}
              className={cn(
                'w-full cursor-pointer',
                isActiveRoute(segment) && 'bg-primary/15 font-medium text-primary'
              )}
            >
              {translate(labelKey)}
            </Link>
          </DropdownMenuItem>
        ))}
        {action && ActionIcon && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              disabled={action.disabled}
              onSelect={action.onSelect}
              className={cn(
                'cursor-pointer',
                action.tone === 'destructive' && 'text-destructive focus:text-destructive'
              )}
            >
              <ActionIcon className="mr-2 h-4 w-4" aria-hidden="true" />
              {action.label}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
