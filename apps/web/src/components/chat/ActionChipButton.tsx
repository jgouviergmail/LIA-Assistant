/**
 * ActionChipButton — the icon chip every action of an assistant bubble wears
 * (Copy, Keep, Share, Download).
 *
 * One chip for the whole row: the same box, the same tooltip carrying the same
 * words as the accessible name (an icon alone is not a name), and a visible
 * focus ring (design system: focus is a ring, never a shadow). Refs and props
 * are forwarded, so a Radix trigger (`DropdownMenuTrigger asChild`) can wrap
 * it like any button.
 */

import * as React from 'react';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

const ACTION_CHIP_BOX =
  'p-1.5 rounded-md border border-border/30 transition-colors ' +
  // The 18px colored drawing uses the existing padding; its layout footprint stays 14px.
  '[&>.app-icon]:size-[18px] [&>.app-icon]:-m-0.5 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

// Selection belongs to the control's box: a multicolour glyph cannot inherit
// the text tint that Lucide uses to distinguish a recorded answer.
const ACTION_CHIP_SELECTED_CLASS =
  'border-primary bg-primary/10 hover:bg-primary/15 ' +
  'dark:bg-primary/15 dark:hover:bg-primary/20';

/** The chip's box — the one every icon action of the bubble row shares. */
export const ACTION_CHIP_CLASS = `${ACTION_CHIP_BOX} bg-background/80 hover:bg-background`;

/**
 * The same box, a shade deeper in either theme: the answers a discussion LIA
 * opened offers, told apart from the bubble's own actions without a new colour.
 */
export const ACTION_CHIP_DEEPER_CLASS =
  `${ACTION_CHIP_BOX} ` +
  'bg-[color-mix(in_srgb,var(--color-background)_94%,var(--color-foreground))] ' +
  'hover:bg-[color-mix(in_srgb,var(--color-background)_89%,var(--color-foreground))] ' +
  'dark:bg-[color-mix(in_srgb,var(--color-background)_62%,black)] ' +
  'dark:hover:bg-[color-mix(in_srgb,var(--color-background)_52%,black)]';

export interface ActionChipButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** The accessible name, and the tooltip — the same words. */
  label: string;
  /** The icon, decorative (`aria-hidden`). */
  children: React.ReactNode;
  /** `deeper` sets a family of answers apart from the row's own actions. */
  tone?: 'default' | 'deeper';
}

export const ActionChipButton = React.forwardRef<HTMLButtonElement, ActionChipButtonProps>(
  function ActionChipButton({ label, children, className, tone = 'default', ...props }, ref) {
    const selected = props['aria-pressed'] === true || props['aria-pressed'] === 'true';
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            ref={ref}
            type="button"
            aria-label={label}
            className={cn(
              tone === 'deeper' ? ACTION_CHIP_DEEPER_CLASS : ACTION_CHIP_CLASS,
              className,
              selected && ACTION_CHIP_SELECTED_CLASS
            )}
            {...props}
          >
            {children}
          </button>
        </TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    );
  }
);
