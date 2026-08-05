/**
 * ScoreLegend — tier legend derived from the shared score-space table.
 *
 * Previously three hand-written copies whose boundaries could drift from
 * the bars they explained; now both read `SCORE_SPACES`.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { SCORE_SPACES, TONE_BAR, type ScoreSpace, tierTone } from '../../utils/tones';

export interface ScoreLegendProps {
  /** Score space whose boundaries the legend explains. */
  space: ScoreSpace;
  /** Additional CSS classes. */
  className?: string;
}

/** Three-tier dot legend for a score space. */
export const ScoreLegend = React.memo(function ScoreLegend({ space, className }: ScoreLegendProps) {
  const { high, medium } = SCORE_SPACES[space];
  const entries = [
    { tier: 'high' as const, label: `≥${high.toFixed(2)}` },
    { tier: 'medium' as const, label: `${medium.toFixed(2)}–${(high - 0.01).toFixed(2)}` },
    { tier: 'low' as const, label: `<${medium.toFixed(2)}` },
  ];

  return (
    <div className={cn('flex items-center gap-3 pt-1 text-[9px] text-muted-foreground', className)}>
      {entries.map(({ tier, label }) => (
        <span key={tier} className="flex items-center gap-1">
          <span className={cn('h-2 w-2 rounded-full', TONE_BAR[tierTone(tier)])} />
          {label}
        </span>
      ))}
    </div>
  );
});
