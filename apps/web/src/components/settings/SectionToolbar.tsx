'use client';

/**
 * SectionToolbar — the ONE header bar of a list-managing settings section
 * (layout program, owner arbitration 2026-08-05).
 *
 * Before it, the three category screens each hand-rolled the same row and
 * each broke it differently on a phone: the create CTA lost its label
 * (`hidden sm:inline`) while "Delete all" kept its own — making the
 * destructive button the most legible one on mobile — and Export simply
 * vanished below `lg`, a feature disparity nothing justified.
 *
 * The contract:
 * - the PRIMARY CTA is solid and ALWAYS labelled (ADR-207 altitude);
 * - SECONDARY actions render inline from `sm` up and fold into a "⋯" menu
 *   below — present at every size, never amputated; a `pinned` secondary
 *   stays INLINE at every size instead (owner arbitration 2026-08-05: Export
 *   on the memory, interests and journals bars — a menu holding one item is
 *   a tap tax, and the folded export read as absent), and the "⋯" menu only
 *   renders when something foldable remains;
 * - the DESTRUCTIVE action stays visible at every size, same geometry as its
 *   neighbours, red saying what it is.
 *
 * Strings arrive translated (ADR-206); confirmation dialogs stay in the
 * caller — this bar only fires `onSelect`.
 */

import type { ReactNode } from 'react';

import type { LucideIcon } from 'lucide-react';
import { MoreHorizontal } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

export interface ToolbarAction {
  key: string;
  /** Already translated. */
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
  disabled?: boolean;
  /** Replaces the icon with a spinner and disables the control. */
  loading?: boolean;
  /**
   * The action is refused for a reason the caller will explain on activation
   * (a cap reached, a quota exhausted): stated with `aria-disabled`, the
   * control stays in the tab order and still fires — `disabled` would blur a
   * focused keyboard user back to `<body>` and hide the reason with the click.
   */
  blocked?: boolean;
  /**
   * Secondary only: render inline at EVERY size instead of folding into the
   * phone "⋯" menu. For actions the reader reaches for often enough that the
   * fold read as absence (Export, per owner arbitration 2026-08-05).
   */
  pinned?: boolean;
}

export interface SectionToolbarProps {
  /** Already translated count line, e.g. "12 memories · 8 active". */
  count?: ReactNode;
  primary: ToolbarAction;
  secondary?: ToolbarAction[];
  destructive?: ToolbarAction;
  /** Accessible name of the phone "⋯" menu holding the secondary actions. */
  menuLabel: string;
}

function ToolbarButton({
  action,
  variant,
  className,
}: {
  action: ToolbarAction;
  variant: 'default' | 'destructive';
  className?: string;
}) {
  const Icon = action.icon;
  return (
    <Button
      type="button"
      size="sm"
      variant={variant}
      onClick={action.onSelect}
      disabled={action.disabled || action.loading}
      aria-disabled={action.blocked || undefined}
      className={className}
    >
      {action.loading ? (
        // Decorative: the control is named by its visible label, and a spinner
        // announcing "loading" would prefix (and break) that name.
        <LoadingSpinner size="default" className="mr-1" aria-hidden="true" />
      ) : (
        // Hidden on phones (owner request 2026-08-05): the label alone is the
        // control there — three labelled buttons must fit a 390px toolbar, and
        // the glyph was the width that pushed the third one off. The state
        // spinner above stays at every size: it carries information the label
        // does not.
        <Icon className="hidden h-4 w-4 sm:mr-1 sm:block" aria-hidden="true" />
      )}
      {action.label}
    </Button>
  );
}

export function SectionToolbar({
  count,
  primary,
  secondary,
  destructive,
  menuLabel,
}: SectionToolbarProps) {
  const pinned = secondary?.filter(action => action.pinned) ?? [];
  const foldable = secondary?.filter(action => !action.pinned) ?? [];
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      {/* Empty string still reserves the slot so the buttons keep their edge. */}
      <div className="text-sm text-muted-foreground">{count}</div>
      {/* `flex-wrap justify-end`: with Export pinned, the four controls
          outgrow a 360px card by ~15px — the destructive one then wraps to a
          right-aligned second row instead of bleeding past the card edge
          (measured 2026-08-05; the parent's wrap cannot help, it only wraps
          the count line against this whole group). */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <ToolbarButton action={primary} variant="default" />
        {pinned.map(action => (
          <ToolbarButton key={action.key} action={action} variant="default" />
        ))}
        {foldable.length > 0 && (
          <>
            <div className="hidden items-center gap-2 sm:flex">
              {foldable.map(action => (
                <ToolbarButton key={action.key} action={action} variant="default" />
              ))}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="sm:hidden"
                  aria-label={menuLabel}
                >
                  <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {foldable.map(action => {
                  const Icon = action.icon;
                  return (
                    <DropdownMenuItem
                      key={action.key}
                      disabled={action.disabled || action.loading}
                      onSelect={action.onSelect}
                    >
                      {action.loading ? (
                        <LoadingSpinner size="default" aria-hidden="true" />
                      ) : (
                        <Icon aria-hidden="true" />
                      )}
                      {action.label}
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        )}
        {destructive && <ToolbarButton action={destructive} variant="destructive" />}
      </div>
    </div>
  );
}
