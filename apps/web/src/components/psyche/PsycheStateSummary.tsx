/**
 * PsycheStateSummary — detailed state card for the settings page.
 *
 * Displays current mood, active emotions, relationship metrics,
 * PAD values, Big Five traits, and drives. All labels translated via i18n.
 *
 * Phase: evolution — Psyche Engine (Iteration 1)
 * Created: 2026-04-01
 */

'use client';

import { useEffect, useRef } from 'react';

import { cn } from '@/lib/utils';
import { getMoodColor } from '@/lib/psyche-colors';
import { usePsycheStore } from '@/stores/psycheStore';
import apiClient from '@/lib/api-client';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PsycheState } from '@/types/psyche';

interface PsycheStateSummaryProps {
  lng: Language;
  /** External refresh trigger — increment to re-fetch state. */
  refreshKey?: number;
}

export function PsycheStateSummary({ lng, refreshKey = 0 }: PsycheStateSummaryProps) {
  const { t } = useTranslation(lng, 'translation');
  const { moodLabel, relationshipStage, enabled, fullState: state } = usePsycheStore();
  const isFirstRender = useRef(true);

  // Refetch state from API when refreshKey changes (skip initial mount)
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    apiClient
      .get<PsycheState>('/psyche/state')
      .then(fresh => usePsycheStore.getState().updateFromFullState(fresh))
      .catch(() => {});
  }, [refreshKey]);

  if (!enabled) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
        {t('psyche.enableDescription', 'Enable psyche engine to see emotional state')}
      </div>
    );
  }

  const moodConfig = getMoodColor(moodLabel);

  return (
    <div className="rounded-lg border p-4 space-y-4">
      {/* ── Mood header ── */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">{moodConfig.icon}</span>
        <div className="flex-1 min-w-0">
          <div className={cn('text-sm font-semibold capitalize', moodConfig.textClass)}>
            {t(`psyche.moods.${moodLabel}`, moodLabel)}
          </div>
          {state && (
            <div className="flex gap-3 mt-0.5">
              {(
                [
                  ['P', state.mood_pleasure, 'text-sky-400'],
                  ['A', state.mood_arousal, 'text-amber-400'],
                  ['D', state.mood_dominance, 'text-violet-400'],
                ] as const
              ).map(([axis, val, color]) => (
                <span key={axis} className={cn('text-[10px] font-mono', color)}>
                  {axis}
                  {val >= 0 ? '+' : ''}
                  {val.toFixed(2)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── PAD bars ── */}
      {state && (
        <div className="space-y-1.5">
          <PadBar
            label={t('psyche.education.mood.pleasure', 'Pleasure')}
            value={state.mood_pleasure}
            color="bg-sky-400"
            negLabel={t('psyche.education.mood.pleasure_neg', 'unhappy')}
            posLabel={t('psyche.education.mood.pleasure_pos', 'happy')}
          />
          <PadBar
            label={t('psyche.education.mood.arousal', 'Arousal')}
            value={state.mood_arousal}
            color="bg-amber-400"
            negLabel={t('psyche.education.mood.arousal_neg', 'calm')}
            posLabel={t('psyche.education.mood.arousal_pos', 'energized')}
          />
          <PadBar
            label={t('psyche.education.mood.dominance', 'Dominance')}
            value={state.mood_dominance}
            color="bg-violet-400"
            negLabel={t('psyche.education.mood.dominance_neg', 'submissive')}
            posLabel={t('psyche.education.mood.dominance_pos', 'assertive')}
          />
        </div>
      )}

      {/* ── Active emotions ── */}
      <div className="space-y-1.5 pt-2 border-t border-border/40">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {t('psyche.activeEmotion', 'Active emotions')}
        </span>
        {state?.active_emotions && state.active_emotions.length > 0 ? (
          <div className="space-y-1.5">
            {state.active_emotions
              .sort((a, b) => b.intensity - a.intensity)
              .map(emo => {
                const pct = Math.round(emo.intensity * 100);
                return (
                  <div key={emo.name} className="flex items-center gap-2 text-xs">
                    <span className="w-24 capitalize font-medium truncate">
                      {t(`psyche.emotions.${emo.name}`, emo.name)}
                    </span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: moodConfig.hex,
                          opacity: 0.4 + emo.intensity * 0.6,
                        }}
                      />
                    </div>
                    <span className="w-8 text-right font-mono text-muted-foreground text-[10px]">
                      {pct}%
                    </span>
                  </div>
                );
              })}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground/50 italic">
            {t('psyche.noActiveEmotion', 'None')}
          </span>
        )}
      </div>

      {/* ── Relationship ── */}
      <div className="pt-2 border-t border-border/40 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {t('psyche.relationshipStage', 'Relationship')}
          </span>
          <span
            className={cn(
              'text-[10px] rounded-full px-2 py-0.5 font-semibold',
              moodConfig.bgClass,
              moodConfig.textClass
            )}
          >
            {t(`psyche.stages.${relationshipStage}`, relationshipStage)}
          </span>
        </div>

        {state && (
          <div className="grid grid-cols-4 gap-2">
            <MiniGauge
              label={t('psyche.depth', 'Depth')}
              value={state.relationship_depth}
              color="bg-emerald-400"
            />
            <MiniGauge
              label={t('psyche.warmth', 'Warmth')}
              value={state.relationship_warmth_active}
              color="bg-orange-400"
            />
            <MiniGauge
              label={t('psyche.trust', 'Trust')}
              value={state.relationship_trust}
              color="bg-sky-400"
            />
            <MiniGauge
              label={t('psyche.curiosityDrive', 'Curiosity')}
              value={state.drive_curiosity}
              color="bg-violet-400"
            />
          </div>
        )}

        {state && (
          <div className="text-[10px] text-muted-foreground/60 text-right">
            {state.relationship_interaction_count} {t('psyche.interactions', 'interactions')}
          </div>
        )}
      </div>

      {/* ── Big Five Traits ── */}
      {state && (
        <div className="pt-2 border-t border-border/40 space-y-2">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {t('psyche.education.traits.title', 'Personality Traits')}
          </span>
          <div className="space-y-1">
            {[
              {
                key: 'O',
                value: state.trait_openness,
                label: t('psyche.education.traits.openness', 'Openness'),
                color: 'bg-violet-400',
              },
              {
                key: 'C',
                value: state.trait_conscientiousness,
                label: t('psyche.education.traits.conscientiousness', 'Conscientiousness'),
                color: 'bg-emerald-400',
              },
              {
                key: 'E',
                value: state.trait_extraversion,
                label: t('psyche.education.traits.extraversion', 'Extraversion'),
                color: 'bg-amber-400',
              },
              {
                key: 'A',
                value: state.trait_agreeableness,
                label: t('psyche.education.traits.agreeableness', 'Agreeableness'),
                color: 'bg-sky-400',
              },
              {
                key: 'N',
                value: state.trait_neuroticism,
                label: t('psyche.education.traits.neuroticism', 'Neuroticism'),
                color: 'bg-rose-400',
              },
            ].map(({ key, value, label, color }) => {
              const pct = Math.round(value * 100);
              return (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-28 text-[10px] text-muted-foreground truncate">{label}</span>
                  <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn('h-full rounded-full transition-all', color)}
                      style={{ width: `${pct}%`, opacity: 0.7 }}
                    />
                  </div>
                  <span className="w-7 text-right text-[10px] font-mono text-muted-foreground">
                    {pct}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── PAD bar: centered at 0, extends left/right with colored fill ── */
function PadBar({
  label,
  value,
  color,
  negLabel,
  posLabel,
}: {
  label: string;
  value: number;
  color: string;
  negLabel: string;
  posLabel: string;
}) {
  const pct = Math.abs(value) * 50;
  const isPositive = value >= 0;

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-[10px]">
        <span className="font-medium text-muted-foreground">{label}</span>
        <span className="font-mono text-muted-foreground/70">
          {value >= 0 ? '+' : ''}
          {value.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-14 text-[9px] text-right text-muted-foreground/50 truncate">
          {negLabel}
        </span>
        <div className="flex-1 h-2 rounded-full bg-muted relative overflow-hidden">
          {/* Center marker */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-muted-foreground/20" />
          {/* Value fill */}
          <div
            className={cn(
              'absolute top-0 bottom-0 rounded-full transition-all duration-500',
              color
            )}
            style={{
              left: isPositive ? '50%' : `${50 - pct}%`,
              width: `${pct}%`,
              opacity: 0.6,
            }}
          />
        </div>
        <span className="w-14 text-[9px] text-muted-foreground/50 truncate">{posLabel}</span>
      </div>
    </div>
  );
}

/* ── Mini circular-style gauge for relationship metrics ── */
function MiniGauge({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100);
  // SVG ring gauge
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - value);

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative w-11 h-11">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 44 44">
          <circle cx="22" cy="22" r={radius} fill="none" className="stroke-muted" strokeWidth="3" />
          <circle
            cx="22"
            cy="22"
            r={radius}
            fill="none"
            className={cn('transition-all duration-700', color.replace('bg-', 'stroke-'))}
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-[9px] font-mono font-semibold">
          {pct}
        </span>
      </div>
      <span className="text-[9px] text-muted-foreground text-center leading-tight truncate max-w-full">
        {label}
      </span>
    </div>
  );
}
