'use client';

import * as React from 'react';
import * as LabelPrimitive from '@radix-ui/react-label';
import { cn } from '@/lib/utils';

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(
      // `block`, never inline: vertical margins are ignored on inline elements,
      // so every `space-y-*` label->control gap silently rendered ~3px whatever
      // its value (measured in-browser 2026-08-05). Flex/grid rows are safe:
      // their items are blockified by the container, and tailwind-merge lets a
      // caller's `flex` win over this base.
      'block text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
      className
    )}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
