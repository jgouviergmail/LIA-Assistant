/**
 * AssistantAvatar — mood smiley avatar for chat messages.
 *
 * Displays the mood smiley with colored ring at full avatar size.
 * Rich tooltip on hover shows psyche state: mood, emotions, drives.
 * Pure component (no hooks, no store) — receives all data via props.
 * Compatible with React.memo() on ChatMessage.
 *
 * Phase: evolution — Psyche Engine v2
 * Created: 2026-04-01
 */

import { useTranslation } from 'react-i18next';

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

/** Emotion intensity → thin bar width class. */
function intensityBarWidth(intensity: number): string {
  const pct = Math.round(intensity * 100);
  if (pct >= 80) return 'w-16';
  if (pct >= 60) return 'w-12';
  if (pct >= 40) return 'w-9';
  if (pct >= 20) return 'w-6';
  return 'w-3';
}

/** Map emotion name to a simple color for the mini-bar. */
const EMOTION_BAR_COLORS: Record<string, string> = {
  // Positive
  joy: 'bg-emerald-400', gratitude: 'bg-cyan-400', pride: 'bg-amber-400',
  amusement: 'bg-pink-400', enthusiasm: 'bg-orange-400', tenderness: 'bg-pink-500',
  playfulness: 'bg-violet-400', relief: 'bg-emerald-300', wonder: 'bg-yellow-400',
  // Negative
  frustration: 'bg-red-400', concern: 'bg-orange-500', melancholy: 'bg-indigo-400',
  disappointment: 'bg-purple-400', nervousness: 'bg-rose-300',
  // Neutral
  curiosity: 'bg-violet-400', serenity: 'bg-sky-400', surprise: 'bg-fuchsia-400',
  empathy: 'bg-teal-400', confusion: 'bg-slate-400', determination: 'bg-sky-500',
  protectiveness: 'bg-teal-500', resolve: 'bg-slate-500',
};

export function AssistantAvatar({ psycheState, tooltipLines, animate }: AssistantAvatarProps) {
  const { t } = useTranslation();

  // Fallback: psyche disabled or no data — show classic "LIA" avatar
  if (!psycheState) {
    return (
      <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm">
        LIA
      </div>
    );
  }

  const moodConfig = getMoodColor(psycheState.mood_label);
  const hasV2Data = psycheState.active_emotions && psycheState.active_emotions.length > 0;

  // Resolve emotions: v2 multi-emotion list, fallback to single
  const emotions: Array<{ name: string; intensity: number }> = hasV2Data
    ? psycheState.active_emotions!
    : psycheState.active_emotion
      ? [{ name: psycheState.active_emotion, intensity: psycheState.emotion_intensity }]
      : [];

  // Drives — only show when significant (> 60%)
  const showCuriosity = (psycheState.drive_curiosity ?? 0) > 0.6;
  const showEngagement = (psycheState.drive_engagement ?? 0) > 0.6;
  const showDrives = showCuriosity || showEngagement;

  return (
    <div className="group relative">
      <div
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center shadow-md ring-2',
          'motion-safe:transition-all motion-safe:duration-500',
          moodConfig.ringClass,
          moodConfig.bgClass,
          animate && 'animate-pulse'
        )}
      >
        <span className="text-xl leading-none">{moodConfig.icon}</span>
      </div>

      {/* Rich tooltip on hover (desktop only) */}
      {(tooltipLines || psycheState) && (
        <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-50 pointer-events-none">
          <div className="bg-popover/95 backdrop-blur-sm border border-border rounded-lg shadow-lg text-xs whitespace-nowrap min-w-[180px]">

            {/* Header: Relationship stage */}
            <div className="px-3 pt-2 pb-1.5 border-b border-border/30">
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted-foreground text-[10px] uppercase tracking-wider">
                  {t('psyche.relationshipStage', 'Relationship')}
                </span>
                <span className="text-foreground font-medium text-[11px]">
                  {t(`psyche.stages.${psycheState.relationship_stage}`, psycheState.relationship_stage)}
                </span>
              </div>
            </div>

            {/* Mood + PAD */}
            <div className="px-3 py-1.5 border-b border-border/30">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-[10px] uppercase tracking-wider w-12 shrink-0">
                  {t('psyche.tooltip.mood', 'Mood')}
                </span>
                <span className="text-foreground font-semibold">
                  {t(`psyche.moods.${psycheState.mood_label}`, psycheState.mood_label)}
                </span>
                {psycheState.mood_intensity && psycheState.mood_intensity !== 'slightly' && (
                  <span className="text-muted-foreground text-[10px] italic">
                    {psycheState.mood_intensity}
                  </span>
                )}
              </div>
              <div className="flex gap-2 mt-0.5 text-[10px] font-mono">
                <span className={padColor(Math.round(psycheState.mood_pleasure * 100))}>
                  P:{Math.round(psycheState.mood_pleasure * 100)}%
                </span>
                <span className={padColor(Math.round(psycheState.mood_arousal * 100))}>
                  A:{Math.round(psycheState.mood_arousal * 100)}%
                </span>
                <span className={padColor(Math.round(psycheState.mood_dominance * 100))}>
                  D:{Math.round(psycheState.mood_dominance * 100)}%
                </span>
              </div>
            </div>

            {/* Emotions with mini intensity bars */}
            {emotions.length > 0 && (
              <div className="px-3 py-1.5 border-b border-border/30">
                <div className="text-muted-foreground text-[10px] uppercase tracking-wider mb-1">
                  {emotions.length === 1
                    ? t('psyche.tooltip.emotion', 'Emotion')
                    : t('psyche.tooltip.emotions', 'Emotions')}
                </div>
                <div className="space-y-0.5">
                  {emotions.map((emo) => (
                    <div key={emo.name} className="flex items-center gap-1.5">
                      <div
                        className={cn(
                          'h-1.5 rounded-full shrink-0',
                          intensityBarWidth(emo.intensity),
                          EMOTION_BAR_COLORS[emo.name] ?? 'bg-muted-foreground',
                        )}
                      />
                      <span className="text-foreground font-medium text-[11px]">
                        {t(`psyche.emotions.${emo.name}`, emo.name)}
                      </span>
                      <span className="text-muted-foreground text-[10px] ml-auto tabular-nums">
                        {Math.round(emo.intensity * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Drives — only when significant */}
            {showDrives && (
              <div className="px-3 py-1.5">
                <div className="flex items-center gap-3">
                  {showCuriosity && (
                    <div className="flex items-center gap-1 text-[10px]">
                      <span className="text-violet-400">⟳</span>
                      <span className="text-muted-foreground">
                        {Math.round((psycheState.drive_curiosity ?? 0) * 100)}%
                      </span>
                    </div>
                  )}
                  {showEngagement && (
                    <div className="flex items-center gap-1 text-[10px]">
                      <span className="text-amber-400">⚡</span>
                      <span className="text-muted-foreground">
                        {Math.round((psycheState.drive_engagement ?? 0) * 100)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
