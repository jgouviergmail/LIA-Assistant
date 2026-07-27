'use client';

/**
 * The way out of a page, on a phone (A2).
 *
 * Below `md` the header's `<nav>` is hidden and nothing replaced it: from the
 * chat, a phone user could reach the dashboard through the logo and NOTHING
 * else — settings and help were unreachable without typing a URL. The logo was
 * already the only interactive landmark up there, so it becomes the entry point
 * rather than adding a burger that would cost width the header does not have
 * (measured: the trailing controls already clip below 380 px).
 *
 * The logo therefore has two forms, mounted exclusively:
 *  - a LINK on `md` and up, where the nav is visible — a menu would duplicate
 *    it and steal the plain "go home" gesture;
 *  - a BUTTON below `md`, opening this menu, whose first item is that same
 *    "go home" destination so nothing is lost.
 *
 * Two elements rather than one element changing role: an element that is a link
 * at one width and a button at another cannot state its role to assistive
 * technology, and would hydrate differently from what the server rendered.
 */

import Link from 'next/link';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DASHBOARD_DESTINATIONS, destinationPath } from '@/lib/dashboard-nav';
import { cn } from '@/lib/utils';

export interface MobileNavMenuProps {
  /** Builds the localized href of a route (the layout's own builder). */
  buildHref: (route: string) => string;
  /** Translates a label key (the layout's `t`). */
  translate: (key: string) => string;
  /** The layout's active-route predicate — single source of truth (no copy). */
  isActiveRoute: (segment: string) => boolean;
  /** Accessible name of the trigger, e.g. "Menu". */
  triggerLabel: string;
}

export function MobileNavMenu({
  buildHref,
  translate,
  isActiveRoute,
  triggerLabel,
}: MobileNavMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={triggerLabel}
          // `h-11` (44 px), not the desktop logo's `h-10`: this is now a
          // CONTROL, and 40 px fails the touch-target floor the header
          // reachability spec enforces — it caught exactly that. The two forms
          // never show together, so the 4 px difference is invisible.
          className="flex h-11 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/80 shadow-md transition-all hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <span className="text-sm font-bold text-primary-foreground">LIA</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        {DASHBOARD_DESTINATIONS.map(({ segment, labelKey }) => (
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
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
