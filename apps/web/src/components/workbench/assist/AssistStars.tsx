'use client';

/**
 * AssistStars — the one mark of what LIA can do in the Tools (ADR-372).
 *
 * Yellow stars say « LIA can help here » on every screen, whatever the person's accent, so the eye
 * learns one sign: a fixed palette, measured in `design-contrast.guard.test.ts`. Only the stars
 * take the colour, never the button behind them. A pure yellow reads at 1.3:1 on the light theme,
 * so there its edge is a darker gold, which carries the contrast while the star stays yellow.
 */
import { Sparkles, type LucideIcon, type LucideProps } from 'lucide-react';
import { forwardRef } from 'react';

import { cn } from '@/lib/utils';

export const AssistStars: LucideIcon = forwardRef<SVGSVGElement, Omit<LucideProps, 'ref'>>(
  function AssistStars({ className, ...props }, ref) {
    return (
      <Sparkles
        ref={ref}
        className={cn('fill-assist-star-fill text-assist-star', className)}
        {...props}
      />
    );
  }
);
