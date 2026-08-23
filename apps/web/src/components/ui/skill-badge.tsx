import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

/**
 * The skill marker: "a skill produced this answer".
 *
 * Cyan is deliberately FIXED here rather than following the user's accent —
 * it is the same signal in the chat and in the landing mockup, and `badge.tsx`
 * records why every other fixed-palette variant was removed. This one earns the
 * exception by being a brand signal rather than a status, and it pays for it by
 * being measured: `design-contrast.guard.test.ts` checks the exact pair below
 * against all ten shipped palettes.
 *
 * Light and dark need different ramp steps. A single value cannot clear AA on
 * both a near-white and a near-black card, which is how `text-cyan-400` came to
 * ship at 1.39:1 in light mode.
 */
const skillBadgeVariants = cva(
  'inline-flex items-center rounded border border-cyan-500/30 bg-cyan-500/20 px-1.5 py-0.5 font-medium tracking-wide text-cyan-800 dark:text-cyan-400',
  {
    variants: {
      size: {
        default: 'text-[10px]',
        sm: 'text-[9px]',
      },
    },
    defaultVariants: {
      size: 'default',
    },
  }
);

export interface SkillBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof skillBadgeVariants> {
  /** Skill identifier, rendered after the sparkle affix. */
  name: string;
  /**
   * Sheen animation. On by default; off for static recreations that must not
   * animate (and for any surface that renders many at once).
   */
  glimmer?: boolean;
}

function SkillBadge({ name, size, glimmer = true, className, ...props }: SkillBadgeProps) {
  return (
    <span
      data-testid="skill-badge"
      className={cn(skillBadgeVariants({ size }), glimmer && 'badge-glimmer', className)}
      {...props}
    >
      {/* Decorative: a screen reader would otherwise announce "black
          four-pointed star" before every skill name. */}
      <span aria-hidden="true">✦</span> {name}
    </span>
  );
}

export { SkillBadge, skillBadgeVariants };
