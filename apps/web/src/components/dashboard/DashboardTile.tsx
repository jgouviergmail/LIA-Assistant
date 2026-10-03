/**
 * The dashboard's tile material, ONE definition for every tile of the page.
 *
 * The briefing cards set it first — a solid card ground, a hairline border,
 * a medium shadow, the theme's primary as a faint wash and a blurred orb in
 * the top-right corner, and an icon in a primary-tinted badge. The results
 * and consumption readouts carried three other recipes (a default card, a
 * thick primary border over a gradient that was partly see-through), so the
 * page read as three families of tile (owner, 2026-10-03). They now draw from
 * these constants; the briefing card keeps its interactive extras (the lift
 * and the orb brightening on hover) on top.
 *
 * Solid on purpose: the page ground is the landing's cosmos
 * (`AppCosmos`), and a tile that lets it through reads as a different
 * kind of surface from its neighbours.
 */

import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils';

/** The tile's frame: shape, solid ground, border, shadow. */
export const DASHBOARD_TILE_FRAME =
  'relative overflow-hidden rounded-2xl border border-border/50 bg-card shadow-[var(--lia-shadow-md)]';

/** The icon badge at the head of a tile; the icon inherits the primary colour. */
export const TILE_ICON_BADGE =
  'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20';

/**
 * The theme's primary wash and orb, painted under the content. The orb
 * brightens on hover only inside a `group` (the interactive briefing card).
 */
export function TileAmbience() {
  return (
    <>
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/8 to-transparent opacity-60 dark:opacity-50"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -top-10 -right-10 h-32 w-32 rounded-full bg-primary opacity-15 blur-3xl transition-opacity duration-500 motion-safe:group-hover:opacity-25"
        aria-hidden="true"
      />
    </>
  );
}

interface DashboardTileProps extends HTMLAttributes<HTMLDivElement> {
  /** Classes of the content layer (padding, layout), above the ambience. */
  contentClassName?: string;
  children: ReactNode;
}

/** A read-only dashboard tile: the frame, the ambience, the content above them. */
export function DashboardTile({
  className,
  contentClassName,
  children,
  ...props
}: DashboardTileProps) {
  return (
    <div className={cn(DASHBOARD_TILE_FRAME, className)} {...props}>
      <TileAmbience />
      <div className={cn('relative', contentClassName)}>{children}</div>
    </div>
  );
}
