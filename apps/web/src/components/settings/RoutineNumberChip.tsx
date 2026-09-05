/**
 * The numbered chip of a routine (ADR-265).
 *
 * ONE component for the two places a routine is numbered — before its title
 * on the card, and on the weekly grid — so a reader correlating the two sees
 * the same glyph. The number is the identity; the colour is the state of ONE
 * slot, which is why the card renders it idle or paused and the grid renders
 * it with the outcome of the day.
 *
 * Purely visual and hidden from assistive technology: the caller owns the
 * accessible name (a `<button>`'s label on the grid, an sr-only text on the
 * card), because what the chip MEANS differs by context and a decorative
 * span cannot know it.
 *
 * Every colour is a theme token pair the contrast guard already covers —
 * `card`, `success`, `destructive`, `warning`, `muted` — so the five states
 * hold in light, dark and OLED alike. A condition routine wears a ring; a
 * routine running right now pulses, and holds still under reduced motion.
 */

import { cn } from '@/lib/utils';
import type { ChipTone } from '@/lib/scheduled-actions';
import type { TriggerKind } from '@/hooks/useScheduledActions';

const TONE_CLASSES: Record<ChipTone, string> = {
  idle: 'bg-card text-foreground border-border shadow-sm',
  success: 'bg-success text-success-foreground border-success',
  failure: 'bg-destructive text-destructive-foreground border-destructive',
  proposed: 'bg-warning text-warning-foreground border-warning',
  paused: 'bg-muted text-muted-foreground border-dashed border-border',
};

export interface RoutineNumberChipProps {
  number: number;
  tone: ChipTone;
  /** A condition routine is EVALUATED at its hour: its chip says so with a ring. */
  kind?: TriggerKind;
  /** Running right now. */
  executing?: boolean;
  className?: string;
}

export function RoutineNumberChip({
  number,
  tone,
  kind = 'time',
  executing = false,
  className,
}: RoutineNumberChipProps) {
  return (
    <span
      aria-hidden="true"
      data-tone={tone}
      data-kind={kind}
      data-executing={executing || undefined}
      className={cn(
        'inline-flex h-5 min-w-5 select-none items-center justify-center rounded-full border px-1',
        'text-[11px] font-semibold leading-none tabular-nums',
        TONE_CLASSES[tone],
        kind === 'condition' && 'ring-2 ring-primary/40 ring-offset-1 ring-offset-background',
        executing && 'animate-pulse motion-reduce:animate-none',
        className
      )}
    >
      {number}
    </span>
  );
}
