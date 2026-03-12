/**
 * Tool Match Row Component
 *
 * Displays a row for a selected tool with its score and confidence.
 * Used in the tool_selection section.
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { formatPercent } from '../../utils/formatters';
import { ConfidenceBadge } from './badges';
import { DEBUG_TEXT_SIZES } from '../../utils/constants';

export interface ToolMatch {
  /** Tool name */
  tool_name: string;
  /** Tool score (0-1) */
  score: number;
  /** Confidence level */
  confidence: 'high' | 'medium' | 'low';
}

export interface ToolMatchRowProps {
  /** Tool match data */
  tool: ToolMatch;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Row displaying a selected tool
 *
 * Design:
 * - Tool name on the left
 * - Score and confidence badge on the right
 * - Green if high confidence, yellow if medium, red if low
 *
 * @example
 * ```tsx
 * <ToolMatchRow
 *   tool={{
 *     tool_name: "search_calendar_events",
 *     score: 0.87,
 *     confidence: "high"
 *   }}
 * />
 * ```
 */
export const ToolMatchRow = React.memo(function ToolMatchRow({
  tool,
  className,
}: ToolMatchRowProps) {
  const { tool_name, score, confidence } = tool;

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 text-xs py-1 px-2 bg-muted/30 rounded',
        className
      )}
    >
      {/* Tool name */}
      <span
        className={`flex-1 truncate font-mono ${DEBUG_TEXT_SIZES.mono} text-foreground`}
        title={tool_name}
      >
        {tool_name}
      </span>

      {/* Score + Confidence badge */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {/* Score */}
        <span
          className={cn(
            `font-mono ${DEBUG_TEXT_SIZES.mono}`,
            confidence === 'high' && 'text-green-700 font-semibold',
            confidence === 'medium' && 'text-yellow-700',
            confidence === 'low' && 'text-red-600'
          )}
        >
          {formatPercent(score)}
        </span>

        {/* Confidence badge */}
        <ConfidenceBadge confidence={confidence} size="xs" />
      </div>
    </div>
  );
});
