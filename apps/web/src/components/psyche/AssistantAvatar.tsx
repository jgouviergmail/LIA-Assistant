/**
 * AssistantAvatar — mood smiley avatar for chat messages.
 *
 * Displays the mood smiley with colored ring at full avatar size.
 * Pure component (no hooks, no store) — receives all data via props.
 * Compatible with React.memo() on ChatMessage.
 *
 * Phase: evolution — Psyche Engine (Iteration 3)
 * Created: 2026-04-01
 */

import { cn } from '@/lib/utils';
import { getMoodColor } from '@/lib/psyche-colors';
import type { PsycheStateSummary } from '@/types/psyche';

export interface AvatarTooltipLine {
  label: string;
  value: string;
  /** Optional PAD values for colored display. */
  pad?: { p: number; a: number; d: number };
}

export interface AssistantAvatarProps {
  /** Psyche state snapshot from message metadata (null if psyche disabled). */
  psycheState?: PsycheStateSummary | null;
  /** Structured tooltip lines (translated by parent). */
  tooltipLines?: AvatarTooltipLine[];
  /** Show a subtle pulse animation (first message, streaming). */
  animate?: boolean;
}

/** Color a PAD percentage: green if positive, red if negative, gray if zero. */
function padColor(val: number): string {
  if (val > 5) return 'text-emerald-400';
  if (val < -5) return 'text-red-400';
  return 'text-muted-foreground';
}

export function AssistantAvatar({
  psycheState,
  tooltipLines,
  animate,
}: AssistantAvatarProps) {
  // Fallback: psyche disabled or no data — show classic "LIA" avatar
  if (!psycheState) {
    return (
      <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm">
        LIA
      </div>
    );
  }

  const moodConfig = getMoodColor(psycheState.mood_label);

  return (
    <div className="group relative">
      <div
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center shadow-md ring-2',
          'motion-safe:transition-all motion-safe:duration-500',
          moodConfig.ringClass,
          moodConfig.bgClass,
          animate && 'animate-pulse',
        )}
      >
        <span className="text-xl leading-none">{moodConfig.icon}</span>
      </div>

      {/* Rich tooltip on hover (desktop only) */}
      {tooltipLines && tooltipLines.length > 0 && (
        <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-50 pointer-events-none">
          <div className="bg-popover/95 backdrop-blur-sm border border-border rounded-lg px-3 py-2 shadow-lg text-xs whitespace-nowrap">
            {tooltipLines.map((line, i) => (
              <div key={i} className="flex items-center gap-1.5 py-0.5">
                <span className="text-muted-foreground">{line.label}:</span>
                <span className="text-foreground font-medium">{line.value}</span>
                {line.pad && (
                  <span className="text-[10px] font-mono ml-1">
                    (<span className={padColor(line.pad.p)}>P:{line.pad.p}%</span>{' '}
                    <span className={padColor(line.pad.a)}>A:{line.pad.a}%</span>{' '}
                    <span className={padColor(line.pad.d)}>D:{line.pad.d}%</span>)
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
