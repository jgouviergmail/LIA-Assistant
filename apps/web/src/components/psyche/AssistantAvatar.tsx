/**
 * AssistantAvatar — selected companion portrait with message-specific emotion.
 *
 * Displays the mood portrait with colored ring at full avatar size.
 * Rich tooltip on hover shows psyche state: mood, emotions, drives.
 * On the latest assistant message (``animateEmoji``) the portrait can play
 * while visible. Frozen native poses (or Spirit WebPs) serve history rows,
 * asset failures and reduced motion. History snapshots wake up while
 * hovered (transient loop), and a mood change on the live avatar plays a
 * one-shot ring ping (micro-interactions batch I1/I6).
 * No store access — receives all data via props (local state covers hover,
 * the ping and the burst). Compatible with React.memo() on ChatMessage.
 * The previous snapshot is kept in state and compared during render — the
 * documented "information from previous renders" pattern, not an effect that
 * sets state (audit A15); whether a change deserves an animation is decided by
 * the pure functions of `avatar-transitions`.
 *
 * Phase: evolution — Psyche Engine v2
 * Created: 2026-04-01
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { prefersReducedMotion } from '@/lib/utils/motion';
import { SelectedCompanionPortrait } from './SelectedCompanionPortrait';
import { emotionBurstGlyph, moodChangePings } from './avatar-transitions';
import type { EyeStyleId } from '@/components/eyes/eye-styles';
import { spiritExpressionForMood, type SpiritVariant } from '@/components/spirit/catalogue';
import { getMoodColor } from '@/lib/psyche-colors';
import type { PsycheStateSummary } from '@/types/psyche';

export interface AssistantAvatarProps {
  /** Psyche state snapshot from message metadata (null if psyche disabled). */
  psycheState?: PsycheStateSummary | null;
  /** Show a subtle pulse animation (first message, streaming). */
  animate?: boolean;
  /** True only for the latest assistant message — permits ongoing portrait playback. */
  animateEmoji?: boolean;
  /** One-shot attention wobble when a proactive notification just arrived (F4). */
  ring?: boolean;
  /** Current identity selection; the emotional snapshot remains message-specific. */
  variant?: SpiritVariant;
  styleId?: EyeStyleId;
  /** The identity preference has been read, so playback can start. */
  animationReady?: boolean;
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
  joy: 'bg-emerald-400',
  gratitude: 'bg-cyan-400',
  pride: 'bg-amber-400',
  amusement: 'bg-pink-400',
  enthusiasm: 'bg-orange-400',
  tenderness: 'bg-pink-500',
  playfulness: 'bg-violet-400',
  relief: 'bg-emerald-300',
  wonder: 'bg-yellow-400',
  // Negative
  frustration: 'bg-red-400',
  concern: 'bg-orange-500',
  melancholy: 'bg-indigo-400',
  disappointment: 'bg-purple-400',
  nervousness: 'bg-rose-300',
  // Neutral
  curiosity: 'bg-violet-400',
  serenity: 'bg-sky-400',
  surprise: 'bg-fuchsia-400',
  empathy: 'bg-teal-400',
  confusion: 'bg-slate-400',
  determination: 'bg-sky-500',
  protectiveness: 'bg-teal-500',
  resolve: 'bg-slate-500',
};

/** Cached v1 summaries carry one emotion; newer message snapshots carry their own list. */
function snapshotEmotions(state: PsycheStateSummary): Array<{ name: string; intensity: number }> {
  if (state.active_emotions?.length) return state.active_emotions;
  return state.active_emotion
    ? [{ name: state.active_emotion, intensity: state.emotion_intensity }]
    : [];
}

/** Normalize optional snapshot drives once for their visibility and percentages. */
function driveLevels(state: PsycheStateSummary) {
  return { curiosity: state.drive_curiosity ?? 0, engagement: state.drive_engagement ?? 0 };
}


/** One-shot particle burst — cleared when the last (most delayed) particle ends. */
function BurstParticles({ glyph, onDone }: { glyph: string; onDone: () => void }) {
  return (
    <span
      className="pointer-events-none absolute inset-x-0 top-0 flex justify-center"
      aria-hidden="true"
    >
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="animate-particle-up absolute top-0 text-xs leading-none"
          style={{
            ['--particle-x' as string]: `${(i - 1) * 14}px`,
            animationDelay: `${i * 120}ms`,
          }}
          onAnimationEnd={i === 2 ? onDone : undefined}
        >
          {glyph}
        </span>
      ))}
    </span>
  );
}

/** Mood label, its intensity when stronger than "slightly", and the PAD triplet. */
function MoodSection({ state }: { state: PsycheStateSummary }) {
  const { t } = useTranslation();
  const pad = [
    ['P', state.mood_pleasure],
    ['A', state.mood_arousal],
    ['D', state.mood_dominance],
  ] as const;
  return (
    <div className="px-3 py-1.5 border-b border-border">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-px-10 uppercase tracking-wider w-12 shrink-0">
          {t('psyche.tooltip.mood', 'Mood')}
        </span>
        <span className="text-foreground font-semibold">
          {t(`psyche.moods.${state.mood_label}`, state.mood_label)}
        </span>
        {state.mood_intensity && state.mood_intensity !== 'slightly' && (
          <span className="text-muted-foreground text-px-10 italic">{state.mood_intensity}</span>
        )}
      </div>
      <div className="flex gap-2 mt-0.5 text-px-10 font-mono">
        {pad.map(([axis, value]) => (
          <span key={axis} className={padColor(Math.round(value * 100))}>
            {axis}:{Math.round(value * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}

/** Emotions with mini intensity bars; nothing when the snapshot carries none. */
function EmotionBars({ emotions }: { emotions: Array<{ name: string; intensity: number }> }) {
  const { t } = useTranslation();
  if (emotions.length === 0) return null;
  return (
    <div className="px-3 py-1.5 border-b border-border">
      <div className="text-muted-foreground text-px-10 uppercase tracking-wider mb-1">
        {emotions.length === 1
          ? t('psyche.tooltip.emotion', 'Emotion')
          : t('psyche.tooltip.emotions', 'Emotions')}
      </div>
      <div className="space-y-0.5">
        {emotions.map(emo => (
          <div key={emo.name} className="flex items-center gap-1.5">
            <div
              className={cn(
                'h-1.5 rounded-full shrink-0',
                intensityBarWidth(emo.intensity),
                EMOTION_BAR_COLORS[emo.name] ?? 'bg-muted-foreground'
              )}
            />
            <span className="text-foreground font-medium text-px-11">
              {t(`psyche.emotions.${emo.name}`, emo.name)}
            </span>
            <span className="text-muted-foreground text-px-10 ml-auto tabular-nums">
              {Math.round(emo.intensity * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Drives — only the significant ones (> 60%), and nothing when none is. */
function DrivesRow({ curiosity, engagement }: { curiosity: number; engagement: number }) {
  const showCuriosity = curiosity > 0.6;
  const showEngagement = engagement > 0.6;
  if (!showCuriosity && !showEngagement) return null;
  return (
    <div className="px-3 py-1.5">
      <div className="flex items-center gap-3">
        {showCuriosity && (
          <div className="flex items-center gap-1 text-px-10">
            <span className="text-violet-400">⟳</span>
            <span className="text-muted-foreground">{Math.round(curiosity * 100)}%</span>
          </div>
        )}
        {showEngagement && (
          <div className="flex items-center gap-1 text-px-10">
            <span className="text-amber-400">⚡</span>
            <span className="text-muted-foreground">{Math.round(engagement * 100)}%</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Rich tooltip on hover (desktop only): relationship, mood, emotions, drives. */
function PsycheTooltip({ state }: { state: PsycheStateSummary }) {
  const { t } = useTranslation();
  return (
    <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-50 pointer-events-none">
      <div className="bg-popover/95 backdrop-blur-sm border border-border rounded-lg shadow-lg text-xs whitespace-nowrap min-w-[180px]">
        {/* Header: Relationship stage */}
        <div className="px-3 pt-2 pb-1.5 border-b border-border">
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground text-px-10 uppercase tracking-wider">
              {t('psyche.relationshipStage', 'Relationship')}
            </span>
            <span className="text-foreground font-medium text-px-11">
              {t(`psyche.stages.${state.relationship_stage}`, state.relationship_stage)}
            </span>
          </div>
        </div>
        <MoodSection state={state} />
        <EmotionBars emotions={snapshotEmotions(state)} />
        <DrivesRow {...driveLevels(state)} />
      </div>
    </div>
  );
}

/**
 * The live avatar's reactions to a change of its snapshot: the mood ping (I6)
 * and the rare-emotion burst (W3).
 *
 * The previous snapshot is kept in state and compared during render (the
 * documented pattern for information from previous renders). A mount, or a
 * history row with its frozen snapshot, never reacts: the previous values start
 * at the mounted ones. A snapshot without psyche is skipped by the mood — the
 * mood before it stays the previous one — while the emotion remembers « none ».
 */
function useSnapshotTransitions(
  psycheState: PsycheStateSummary | null | undefined,
  live: boolean
) {
  const [pinging, setPinging] = useState(false);
  const moodLabel = psycheState?.mood_label ?? null;
  const [previousMood, setPreviousMood] = useState(moodLabel);
  if (moodLabel !== null && moodLabel !== previousMood) {
    setPreviousMood(moodLabel);
    if (moodChangePings(previousMood, moodLabel, live)) setPinging(true);
  }
  const [burstGlyph, setBurstGlyph] = useState<string | null>(null);
  const activeEmotion = psycheState?.active_emotion ?? null;
  const [previousEmotion, setPreviousEmotion] = useState(activeEmotion);
  if (activeEmotion !== previousEmotion) {
    setPreviousEmotion(activeEmotion);
    const glyph = emotionBurstGlyph(
      previousEmotion,
      activeEmotion,
      psycheState?.emotion_intensity ?? 0,
      live,
      prefersReducedMotion()
    );
    if (glyph) setBurstGlyph(glyph);
  }
  return {
    pinging,
    endPing: () => setPinging(false),
    burstGlyph,
    endBurst: () => setBurstGlyph(null),
  };
}

export function AssistantAvatar({
  psycheState,
  animate,
  animateEmoji,
  ring,
  variant = 'female',
  styleId = 'spirit',
  animationReady = true,
}: AssistantAvatarProps) {
  // Hover-wake (I1): history snapshots animate while hovered — transient,
  // one loop at a time, the permanent loop stays exclusive to animateEmoji.
  const [hovered, setHovered] = useState(false);
  const live = Boolean(animateEmoji);
  const { pinging, endPing, burstGlyph, endBurst } = useSnapshotTransitions(psycheState, live);
  const portraitAnimates = animationReady && (live || hovered);

  // The selected identity remains visible even without an emotional snapshot.
  if (!psycheState) {
    return (
      <div
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm',
          ring && 'animate-bell-ring'
        )}
      >
        <SelectedCompanionPortrait
          styleId={styleId}
          variant={variant}
          expression="neutral"
          animate={portraitAnimates}
        />
      </div>
    );
  }

  const moodConfig = getMoodColor(psycheState.mood_label);

  return (
    // role="presentation": hover handlers only drive the visual hover state —
    // the avatar exposes no action here (audit F012/F045).
    <div
      role="presentation"
      className={cn('group relative', ring && 'animate-bell-ring')}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center shadow-md ring-2',
          'motion-safe:transition-all motion-safe:duration-500',
          moodConfig.ringClass,
          moodConfig.bgClass,
          animate && 'motion-safe:animate-pulse',
          pinging && 'animate-mood-ping'
        )}
        onAnimationEnd={e => {
          if (e.animationName === 'mood-ping') endPing();
        }}
      >
        {/* The identity follows the current choice; historical moods stay frozen. */}
        <SelectedCompanionPortrait
          styleId={styleId}
          variant={variant}
          expression={spiritExpressionForMood(psycheState.mood_label)}
          animate={portraitAnimates}
        />
      </div>

      {burstGlyph && <BurstParticles glyph={burstGlyph} onDone={endBurst} />}

      <PsycheTooltip state={psycheState} />
    </div>
  );
}
