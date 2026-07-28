'use client';

import type { LucideIcon } from 'lucide-react';

import { TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

/**
 * The settings tab bar — persistent while the page scrolls.
 *
 * The settings page stacks ~30 accordion sections over two or three tabs. Once
 * the reader is a few screens down, the tabs are gone: there is no way to tell
 * which tab is open, and switching means scrolling all the way back up. The bar
 * therefore sticks under the dashboard header (`top-16` = its `h-16`).
 *
 * Sticky positioning only became possible with ADR-171 — `body` was a scroll
 * container that no descendant could stick to.
 *
 * The tabs keep the layout the page always had, on desktop AND on mobile:
 * equal shares of the row, content centred, icon included, `text-sm`.
 *
 * The single behavioural change is that a label can no longer ESCAPE its
 * button. Measured with the real font, three equal columns need 422 px (de) to
 * 488 px (it) while a 390 px phone offers 358 px, so `whitespace-nowrap` used
 * to push "Einstellungen" past its own tab, and the overflow was then clipped
 * at the screen edge — silently. `min-w-0` (a grid item otherwise never
 * shrinks below its content) plus `truncate` turns that invisible cut into an
 * explicit ellipsis. Desktop is wide enough that nothing is ever truncated, so
 * there it is a no-op.
 */
export interface SettingsTabDescriptor {
  /** Radix tab value — must match the `TabsContent` it drives. */
  value: string;
  /** Already-translated label (the page owns the dictionary). */
  label: string;
  icon: LucideIcon;
}

export interface SettingsTabsBarProps {
  tabs: readonly SettingsTabDescriptor[];
}

export function SettingsTabsBar({ tabs }: SettingsTabsBarProps) {
  return (
    <div
      className={cn(
        'sticky top-16 z-30 border-b border-border/40 py-2',
        // Opaque enough to stay readable over the cards scrolling beneath it.
        'bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80',
        // Bleed to the edges of <main>'s padding so the backdrop spans the full
        // width instead of leaving two transparent gutters.
        '-mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8'
      )}
    >
      {/* `auto-cols-fr` + `grid-flow-col`: equal shares whatever the tab count
          (two tabs for a regular user, three for a superuser) — no lookup table
          that a fourth tab would silently fall through. */}
      <TabsList className="grid w-full auto-cols-fr grid-flow-col">
        {tabs.map(({ value, label, icon: Icon }) => (
          <TabsTrigger
            key={value}
            value={value}
            // Same look as ever — equal share, centred content, icon, `text-sm`.
            // The one addition is `min-w-0`, without which a grid item never
            // shrinks below its content: the label then ran past its own button
            // and was clipped at the screen edge. With it, `truncate` ends the
            // label with an ellipsis instead. Desktop is wide enough that
            // nothing is ever cut, so this is invisible there.
            className="min-w-0 gap-2"
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{label}</span>
          </TabsTrigger>
        ))}
      </TabsList>
    </div>
  );
}
