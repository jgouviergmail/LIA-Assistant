import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * The native checkbox, themed on the palette tokens.
 *
 * Replaces three hand-rolled copies that carried `text-primary-600
 * focus:ring-primary-500 border-gray-300`. Those class names compile to NOTHING
 * — the palette exposes `--color-primary`, not a numeric ramp — so the boxes
 * had no accent and no focus ring, and `border-gray-300` had no dark variant.
 *
 * Native rather than Radix on purpose: form semantics, `required`, autofill and
 * submission come for free, no dependency is added, and the dev container's
 * lockfile split (a `pnpm add` inside the container leaves the host stale) is
 * avoided entirely. `accent-primary` themes the browser's own check mark, which
 * keeps the control's platform behaviour and high-contrast-mode handling.
 *
 * Do NOT grow the pointer target with a `::before` pseudo-element. It looks
 * like it works and it does not, portably: measured 2026-08-23 on the three
 * engines, a 24×24 centred `::before` on this input extends the hit area in
 * Chromium and WebKit and has NO EFFECT in Firefox (`elementFromPoint` 10px
 * outside the box returns `HTML`, exactly as with no pseudo-element at all).
 * An accessibility guarantee that holds in two engines out of three is not a
 * guarantee — it is a silent gap on the one engine nobody tests by default.
 *
 * The box therefore stays at the native 16×16, and WCAG 2.5.8 is met the way
 * the criterion intends for a labelled checkbox: the associated `<label for>`
 * is part of the same target, and the spacing exception covers the rest.
 */
export type CheckboxProps = Omit<React.ComponentPropsWithoutRef<'input'>, 'type'>;

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-4 w-4 shrink-0 cursor-pointer rounded border-input accent-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
      // AFTER the spread, and excluded from the props type: a stray
      // `type="text"` would otherwise produce a text field wearing a
      // checkbox's styling, and its `role` would change with it.
      type="checkbox"
    />
  )
);
Checkbox.displayName = 'Checkbox';

export { Checkbox };
