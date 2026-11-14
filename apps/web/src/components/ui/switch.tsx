'use client';

import * as React from 'react';
import * as SwitchPrimitives from '@radix-ui/react-switch';
import { cn } from '@/lib/utils';

type SwitchProps = React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root> & {
  /**
   * A save this switch's change started, or its section's, is on its way. The switch stays
   * focusable and says so (`aria-busy`, `aria-disabled`) and ignores a toggle. Never
   * `disabled` for this: disabling the control that holds the focus throws the keyboard
   * to `<body>` (measured 2026-11-13); `disabled` stays for what cannot be switched at all.
   */
  busy?: boolean;
};

const Switch = React.forwardRef<React.ElementRef<typeof SwitchPrimitives.Root>, SwitchProps>(
  ({ className, busy = false, onClick, ...props }, ref) => (
    <SwitchPrimitives.Root
      className={cn(
        'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
        className
      )}
      {...props}
      onClick={event => {
        onClick?.(event);
        // Radix toggles only when the click's default still holds: a busy switch refuses.
        if (busy) event.preventDefault();
      }}
      aria-busy={busy || undefined}
      aria-disabled={busy || props['aria-disabled']}
      ref={ref}
    >
      <SwitchPrimitives.Thumb
        className={cn(
          'pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0'
        )}
      />
    </SwitchPrimitives.Root>
  )
);
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
