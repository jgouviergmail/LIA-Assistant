'use client';

/**
 * RowActions — the ONE way a list row exposes its actions (owner arbitration
 * 2026-08-05, layout program).
 *
 * Before this component the three category screens had three patterns:
 * hover-revealed buttons (invisible to a keyboard user, whose focus lands on
 * `opacity-0` controls), a tap-anywhere card handler gated on
 * `window.innerWidth`, and a full-screen mobile Dialog duplicated per screen.
 * ADR-207's lesson generalises: an affordance the pointer must reveal is not
 * an affordance.
 *
 * - From `sm` up: one ghost icon button per action, ALWAYS visible, the
 *   destructive one carrying its red at rest (the passkeys pattern).
 * - Below `sm`: a single "⋮" trigger opening a lightweight DropdownMenu —
 *   one tap fewer than the old Dialog, and the same component everywhere.
 *
 * Strings come translated from the caller (ADR-206: a primitive never invents
 * a user-facing string); `menuLabel` must NAME THE ROW ("Actions — Standup"),
 * because on a list every anonymous "⋮" reads the same to a screen reader.
 */

import type { LucideIcon } from 'lucide-react';
import { MoreVertical } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { cn } from '@/lib/utils';

export interface RowAction {
  /** Stable identity of the action within the row. */
  key: string;
  /** Already translated; becomes the accessible name on both renderings. */
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
  /** `destructive` carries red at rest — never revealed by hover only. */
  tone?: 'default' | 'destructive';
  disabled?: boolean;
  /** Replaces the icon with a spinner and disables the control. */
  loading?: boolean;
  /**
   * Refused for a reason the caller explains on activation (a cap reached):
   * stated with `aria-disabled`, still focusable, still fires — `disabled`
   * would hide the reason with the click.
   */
  blocked?: boolean;
  /** Extra classes for the `sm+` icon button (e.g. a pinned state tint). */
  iconClassName?: string;
  /**
   * A navigation rather than a handler (a file download): both renderings
   * become real links the browser handles, `onSelect` is then unused.
   */
  href?: string;
}

export interface RowActionsProps {
  actions: RowAction[];
  /**
   * Accessible name of the phone "⋮" trigger. Must identify the row, not just
   * say "actions": a list renders one trigger per row.
   */
  menuLabel: string;
  className?: string;
}

export function RowActions({ actions, menuLabel, className }: RowActionsProps) {
  return (
    <div className={cn('flex shrink-0 items-center', className)}>
      {/* sm+: every action one tap away, none hidden behind a hover. */}
      <div className="hidden gap-1 sm:flex">
        {actions.map(action => {
          const Icon = action.icon;
          const glyph = action.loading ? (
            <LoadingSpinner size="default" />
          ) : (
            <Icon className="h-4 w-4" aria-hidden="true" />
          );
          const className = cn(
            action.tone === 'destructive' && 'text-destructive hover:text-destructive',
            action.iconClassName
          );
          if (action.href) {
            return (
              <Button key={action.key} variant="ghost" size="icon" asChild className={className}>
                <a href={action.href} download aria-label={action.label} title={action.label}>
                  {glyph}
                </a>
              </Button>
            );
          }
          return (
            <Button
              key={action.key}
              type="button"
              variant="ghost"
              size="icon"
              aria-label={action.label}
              title={action.label}
              disabled={action.disabled || action.loading}
              aria-disabled={action.blocked || undefined}
              onClick={action.onSelect}
              className={className}
            >
              {glyph}
            </Button>
          );
        })}
      </div>

      {/* Phone: one ⋮ → a menu, not a full-screen dialog. */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="sm:hidden"
            aria-label={menuLabel}
          >
            <MoreVertical className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {actions.map(action => {
            const Icon = action.icon;
            const content = (
              <>
                {action.loading ? (
                  // Decorative: the item is named by its visible label.
                  <LoadingSpinner size="default" aria-hidden="true" />
                ) : (
                  <Icon aria-hidden="true" />
                )}
                {action.label}
              </>
            );
            const className = cn(
              action.tone === 'destructive' && 'text-destructive focus:text-destructive'
            );
            if (action.href) {
              return (
                <DropdownMenuItem key={action.key} asChild className={className}>
                  <a href={action.href} download>
                    {content}
                  </a>
                </DropdownMenuItem>
              );
            }
            return (
              <DropdownMenuItem
                key={action.key}
                disabled={action.disabled || action.loading}
                aria-disabled={action.blocked || undefined}
                onSelect={action.onSelect}
                className={className}
              >
                {content}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
