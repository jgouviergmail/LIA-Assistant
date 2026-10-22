/** Complete, observation-only psyche state for the settings page. */
'use client';

import { useEffect, useId, useState, type ReactNode } from 'react';
import { ChartScatter, Compass, Brain, Heart, MessageCircle, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AnimatedEmoji } from '@/components/ui/animated-emoji';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Disclosure } from '@/components/ui/disclosure';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { getMoodColor } from '@/lib/psyche-colors';
import { usePsycheStore } from '@/stores/psycheStore';
import apiClient from '@/lib/api-client';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ActiveEmotion, PsycheState } from '@/types/psyche';
import { PsycheEfficacy } from './PsycheEfficacy';

interface PsycheStateSummaryProps {
  lng: Language;
  refreshKey?: number;
  summary?: ReactNode;
}

export function PsycheStateSummary({ lng, refreshKey = 0, summary }: PsycheStateSummaryProps) {
  const snapshot = usePsycheStore();
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const belongsToAccount = !!user?.id && snapshot.ownerId === user.id;
  const state =
    belongsToAccount && snapshot.fullState?.user_id === user?.id ? snapshot.fullState : null;
  const enabled = belongsToAccount && snapshot.enabled;

  useEffect(() => {
    if (refreshKey === 0 || !enabled) return;
    const controller = new AbortController();
    // Strict Mode's probe is cleaned up before it can reach the server.
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted || !isCurrent()) return;
      try {
        const fresh = await apiClient.get<PsycheState | null>('/psyche/state?initialize=false', {
          signal: controller.signal,
        });
        const store = usePsycheStore.getState();
        if (controller.signal.aborted || !isCurrent() || store.ownerId !== user?.id) return;
        if (fresh === null) store.clearObservedState();
        else if (fresh.user_id === user?.id) store.updateFromFullState(fresh);
      } catch {
        // Retain the last confirmed observation if a follow-up read fails.
      }
    });
    return () => controller.abort();
  }, [refreshKey, enabled, isCurrent, user?.id]);

  return (
    <StateOverview state={enabled ? state : null} enabled={enabled} lng={lng} summary={summary} />
  );
}

function StateOverview({
  state,
  enabled,
  lng,
  summary,
}: {
  state: PsycheState | null;
  enabled: boolean;
  lng: Language;
  summary?: ReactNode;
}) {
  const { t } = useTranslation(lng, 'translation');
  const [moodOpen, setOpen] = useState('mood');
  return (
    <div className="min-w-0 space-y-4">
      <Card surface="nested" variant="flat" className="min-w-0 border-border px-4 sm:px-6">
        {summary && <div className="border-b border-border py-5">{summary}</div>}
        {state ? (
          <>
            <Accordion type="single" collapsible value={moodOpen} onValueChange={setOpen}>
              <AccordionItem value="mood" className="min-w-0 border-0">
                <AccordionTrigger className="gap-3 py-3 text-left text-sm font-medium hover:no-underline">
                  <span className="flex min-w-0 items-center gap-2">
                    <Brain className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    <span className="min-w-0 break-words">{t('psyche.presentation.mood')}</span>
                  </span>
                </AccordionTrigger>
                <AccordionContent className="min-w-0 pb-5">
                  <div className="grid min-w-0 gap-7 md:grid-cols-2 md:gap-8">
                    <EmotionOrbits state={state} lng={lng} />
                    <PadPlane state={state} lng={lng} />
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
            <div className="border-t border-border pb-3">
              <OceanTraits state={state} lng={lng} />
            </div>
          </>
        ) : (
          <p className="py-5 text-sm text-muted-foreground">
            {t(enabled ? 'psyche.stateUnavailable' : 'psyche.enableDescription')}
          </p>
        )}
      </Card>
      {state && (
        <>
          <BehaviorOverview state={state} lng={lng} />
          <PsycheEfficacy profile={state.efficacy_profile} lng={lng} />
        </>
      )}
    </div>
  );
}

const EMOTION_STROKES = ['var(--color-primary)', '#10b981', '#8b5cf6'] as const;
const clampUnit = (value: number) => Math.min(1, Math.max(0, value));
const clampPad = (value: number) => Math.min(1, Math.max(-1, value));
const signedValue = (value: number, lng: Language) =>
  `${value >= 0 ? '+' : ''}${value.toLocaleString(lng, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function EmotionOrbits({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const mood = getMoodColor(state.mood_label);
  const [hovered, setHovered] = useState(false);
  const emotions = [...state.active_emotions].sort((a, b) => b.intensity - a.intensity);
  const hintId = useId();
  return (
    <section
      aria-label={t('psyche.activeEmotion')}
      aria-describedby={hintId}
      className="min-w-0 rounded-lg border border-border bg-card p-3"
    >
      <div
        className="relative mx-auto aspect-square w-full max-w-[280px]"
        role="presentation"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <svg viewBox="0 0 280 280" aria-hidden="true" className="block size-full">
          {emotions.slice(0, 3).map((emotion, index) => (
            <EmotionArc key={emotion.name} emotion={emotion} index={index} />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-14 text-center">
          <AnimatedEmoji
            glyph={mood.icon}
            codepoint={mood.codepoint}
            animate={hovered}
            imgClassName="size-14"
            spanClassName="text-5xl"
          />
          <p className={cn('max-w-full break-words text-xl font-semibold', mood.textClass)}>
            {t(`psyche.moods.${state.mood_label}`, state.mood_label)}
          </p>
        </div>
      </div>
      <div className="mx-auto mt-3 max-w-sm space-y-3">
        {emotions.map((emotion, index) => (
          <div
            key={emotion.name}
            role="meter"
            aria-label={t(`psyche.emotions.${emotion.name}`, emotion.name)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(emotion.intensity * 100)}
            aria-valuetext={`${Math.round(emotion.intensity * 100)}%`}
            className="flex min-w-0 items-start gap-2 text-sm"
          >
            <span
              aria-hidden="true"
              className="mt-1.5 size-2 shrink-0 rounded-full"
              style={{ backgroundColor: EMOTION_STROKES[index] ?? mood.hex }}
            />
            <span className="min-w-0 flex-1 break-words">
              {t(`psyche.emotions.${emotion.name}`, emotion.name)}
            </span>
            <span className="shrink-0 font-semibold tabular-nums">
              {Math.round(emotion.intensity * 100)} %
            </span>
          </div>
        ))}
        {emotions.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">{t('psyche.noActiveEmotion')}</p>
        )}
      </div>
      <p id={hintId} className="sr-only">
        {t('psyche.presentation.emotionRingsHint')}
      </p>
    </section>
  );
}

function EmotionArc({ emotion, index }: { emotion: ActiveEmotion; index: number }) {
  const radius = 84 + index * 18;
  const circumference = 2 * Math.PI * radius;
  const intensity = clampUnit(emotion.intensity);
  return (
    <g>
      <circle
        cx="140"
        cy="140"
        r={radius}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="7"
        strokeOpacity="0.6"
      />
      <circle
        cx="140"
        cy="140"
        r={radius}
        fill="none"
        stroke={EMOTION_STROKES[index]}
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${circumference * intensity} ${circumference * (1 - intensity)}`}
        transform="rotate(-90 140 140)"
      />
    </g>
  );
}

function PadPlane({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const gridId = useId().replace(/:/g, '');
  const descriptionId = useId();
  const pleasure = clampPad(state.mood_pleasure);
  const arousal = clampPad(state.mood_arousal);
  const x = 171 + pleasure * 121;
  const y = 129 - arousal * 99;
  const values = [
    [t('psyche.education.mood.pleasure'), state.mood_pleasure],
    [t('psyche.education.mood.arousal'), state.mood_arousal],
    [t('psyche.education.mood.dominance'), state.mood_dominance],
  ] as const;
  return (
    <section className="min-w-0 rounded-lg border border-border bg-card p-3">
      <InstrumentHeading icon={ChartScatter} title={t('psyche.presentation.padTitle')} />
      <svg
        viewBox="0 0 330 258"
        role="img"
        aria-label={t('psyche.presentation.padTitle')}
        aria-describedby={descriptionId}
        className="mx-auto mt-3 block w-full max-w-[390px]"
      >
        <defs>
          <pattern id={gridId} width="22" height="22" patternUnits="userSpaceOnUse">
            <path d="M22 0H0V22" fill="none" stroke="var(--color-border)" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect
          x="50"
          y="30"
          width="242"
          height="198"
          rx="12"
          fill={`url(#${gridId})`}
          stroke="var(--color-border)"
          strokeOpacity="0.4"
        />
        <path
          d="M171 30V228M50 129H292"
          fill="none"
          stroke="var(--color-muted-foreground)"
          strokeWidth="1"
          strokeOpacity="0.45"
        />
        <g fill="var(--color-muted-foreground)" fontSize="12">
          <text x="50" y="249">
            −1
          </text>
          <text x="166" y="249">
            0
          </text>
          <text x="280" y="249">
            +1
          </text>
          <text x="24" y="36">
            +1
          </text>
          <text x="28" y="133">
            0
          </text>
          <text x="24" y="230">
            −1
          </text>
          <text x="171" y="18" textAnchor="middle">
            {t('psyche.education.mood.arousal')}
          </text>
        </g>
        <path
          d={`M${x} 129V${y}H171`}
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth="1"
          strokeOpacity="0.6"
          strokeDasharray="3 4"
        />
        <circle cx={x} cy={y} r="17" fill="var(--color-primary)" fillOpacity="0.12" />
        <circle
          cx={x}
          cy={y}
          r="6"
          fill="var(--color-primary)"
          stroke="var(--color-card)"
          strokeWidth="2"
        />
      </svg>
      <p className="text-center text-xs text-muted-foreground">
        {t('psyche.education.mood.pleasure')}
      </p>
      <dl className="mt-5 grid grid-cols-3 gap-2">
        {values.map(([label, value]) => (
          <div key={label} className="min-w-0 text-center">
            <dt className="break-words text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-2 text-lg font-semibold tabular-nums text-primary">
              <span
                role="meter"
                aria-label={label}
                aria-valuemin={-1}
                aria-valuemax={1}
                aria-valuenow={value}
                aria-valuetext={signedValue(value, lng)}
              >
                {signedValue(value, lng)}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      <p id={descriptionId} className="sr-only">
        {values.map(([label, value]) => `${label} ${signedValue(value, lng)}`).join(', ')}.{' '}
        {t('psyche.presentation.padHint')}
      </p>
    </section>
  );
}

function BehaviorOverview({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const [open, setOpen] = useState<string[]>(['relationship', 'drives']);
  const stageId = useId();
  const relationshipTitle = t('psyche.presentation.relationship');
  const drivesTitle = t('psyche.presentation.drivesTitle');
  return (
    <Card surface="nested" variant="flat" className="min-w-0 border-border">
      <Accordion
        type="multiple"
        value={open}
        onValueChange={setOpen}
        className="grid min-w-0 md:grid-cols-2"
      >
        <AccordionItem
          value="relationship"
          className="min-w-0 border-b border-border px-4 sm:px-6 md:border-b-0 md:border-r"
        >
          <AccordionTrigger
            aria-label={relationshipTitle}
            aria-describedby={stageId}
            className="gap-3 py-3 text-left text-sm font-medium hover:no-underline"
          >
            <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-2">
              <span className="flex min-w-0 flex-[1_1_12rem] items-center gap-2">
                <Heart aria-hidden="true" className="size-4 shrink-0 text-primary" />
                <span className="min-w-0 break-words">{relationshipTitle}</span>
              </span>
              <Badge id={stageId} variant="default" className="max-w-full whitespace-normal">
                {t(`psyche.stages.${state.relationship_stage}`, state.relationship_stage)}
              </Badge>
            </span>
          </AccordionTrigger>
          <AccordionContent className="min-w-0 pb-5">
            <Relationship state={state} lng={lng} />
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="drives" className="min-w-0 border-0 px-4 sm:px-6">
          <AccordionTrigger
            aria-label={drivesTitle}
            className="gap-3 py-3 text-left text-sm font-medium hover:no-underline"
          >
            <span className="flex min-w-0 items-center gap-2">
              <Compass aria-hidden="true" className="size-4 shrink-0 text-primary" />
              <span className="min-w-0 break-words">{drivesTitle}</span>
            </span>
          </AccordionTrigger>
          <AccordionContent className="min-w-0 pb-5">
            <DriveLevels state={state} lng={lng} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
  );
}

function Relationship({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  return (
    <div className="min-w-0">
      {' '}
      <div className="my-6 grid grid-cols-[repeat(auto-fit,minmax(min(100%,5em),1fr))] gap-2 sm:gap-4">
        <RingMeter label={t('psyche.depth')} value={state.relationship_depth} />
        <RingMeter label={t('psyche.warmth')} value={state.relationship_warmth_active} />
        <RingMeter label={t('psyche.trust')} value={state.relationship_trust} />
      </div>
      <p className="flex flex-wrap items-center justify-center gap-1.5 text-sm text-muted-foreground">
        <MessageCircle aria-hidden="true" className="size-4 shrink-0" />
        <span className="font-semibold tabular-nums text-foreground">
          {state.relationship_interaction_count.toLocaleString(lng)}
        </span>
        <span>{t('psyche.interactions')}</span>
      </p>
    </div>
  );
}

function RingMeter({ label, value }: { label: string; value: number }) {
  const circumference = 2 * Math.PI * 37;
  const percent = Math.round(value * 100);
  const fill = clampUnit(value);
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent}%`}
      className="flex min-w-0 flex-col items-center gap-2"
    >
      <div className="relative aspect-square w-full max-w-[5.75em]">
        <svg viewBox="0 0 92 92" aria-hidden="true" className="block size-full">
          <circle cx="46" cy="46" r="37" fill="none" stroke="var(--color-border)" strokeWidth="4" />
          <circle
            cx="46"
            cy="46"
            r="37"
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={`${circumference * fill} ${circumference * (1 - fill)}`}
            transform="rotate(-90 46 46)"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center gap-0.5 text-xl font-semibold tabular-nums">
          {percent}
          <span className="text-xs font-normal text-muted-foreground">%</span>
        </span>
      </div>
      <span className="max-w-full break-words text-center text-sm">{label}</span>
    </div>
  );
}

function DriveLevels({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  return (
    <div className="min-w-0">
      <div className="space-y-6 py-6">
        <PercentMeter
          label={t('psyche.curiosityDrive')}
          value={state.drive_curiosity}
          color="bg-primary"
        />
        <PercentMeter
          label={t('psyche.history.engagement')}
          value={state.drive_engagement}
          color="bg-primary"
        />
      </div>
      <p className="sr-only">{t('psyche.presentation.drivesHint')}</p>
    </div>
  );
}

function OceanTraits({ state, lng }: { state: PsycheState; lng: Language }) {
  const { t } = useTranslation(lng, 'translation');
  const traits = [
    ['O', t('psyche.education.traits.openness'), state.trait_openness],
    ['C', t('psyche.education.traits.conscientiousness'), state.trait_conscientiousness],
    ['E', t('psyche.education.traits.extraversion'), state.trait_extraversion],
    ['A', t('psyche.education.traits.agreeableness'), state.trait_agreeableness],
    ['N', t('psyche.education.traits.neuroticism'), state.trait_neuroticism],
  ] as const;
  const position = (index: number, value: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / 5;
    return [160 + Math.cos(angle) * 102 * value, 149 + Math.sin(angle) * 102 * value];
  };
  const polygon = (scale: number) =>
    traits.map((_, index) => position(index, scale).join(',')).join(' ');
  const current = traits.map(([, , value], index) => position(index, clampUnit(value)));
  return (
    <Disclosure
      defaultOpen
      icon={Brain}
      title={t('psyche.education.traits.title')}
      titleClassName="whitespace-normal"
      surface="primary"
      className="border-border px-3"
    >
      <div className="grid min-w-0 items-center gap-5 pt-3 md:grid-cols-2">
        <svg
          viewBox="0 0 320 280"
          aria-hidden="true"
          className="mx-auto block w-full max-w-[320px]"
        >
          <g fill="none" stroke="var(--color-border)" strokeWidth="1">
            {[0.25, 0.5, 0.75, 1].map(scale => (
              <polygon key={scale} points={polygon(scale)} />
            ))}
            {traits.map(([key], index) => (
              <path key={key} d={`M160 149L${position(index, 1).join(' ')}`} />
            ))}
          </g>
          <polygon
            points={current.map(point => point.join(',')).join(' ')}
            fill="var(--color-primary)"
            fillOpacity="0.12"
            stroke="var(--color-primary)"
            strokeWidth="2"
          />
          {current.map(([x, y], index) => (
            <circle key={traits[index][0]} cx={x} cy={y} r="4" fill="var(--color-primary)" />
          ))}
          {traits.map(([key], index) => {
            const [x, y] = position(index, 1.25);
            return (
              <text
                key={key}
                x={x}
                y={y + 5}
                textAnchor="middle"
                fill="var(--color-muted-foreground)"
                fontSize="14"
              >
                {key}
              </text>
            );
          })}
        </svg>
        <dl className="min-w-0 divide-y divide-border">
          {traits.map(([key, label, value]) => (
            <div key={key} className="flex min-w-0 flex-wrap items-start gap-2 py-3 text-sm">
              <dt className="flex min-w-0 flex-[1_1_10em] flex-wrap items-start gap-2">
                <span aria-hidden="true" className="w-[1em] shrink-0 font-semibold text-primary">
                  {key}
                </span>
                <span className="min-w-0 flex-[1_1_min-content] break-words">{label}</span>
              </dt>
              <dd className="ml-auto shrink-0 font-semibold tabular-nums">
                <span
                  role="meter"
                  aria-label={label}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(value * 100)}
                  aria-valuetext={`${Math.round(value * 100)}%`}
                >
                  {Math.round(value * 100)} %
                </span>
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </Disclosure>
  );
}

function InstrumentHeading({ title, icon: Icon }: { title: string; icon: LucideIcon }) {
  return (
    <h4 className="flex min-w-0 items-start gap-2 text-sm font-semibold">
      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
      <span className="min-w-0 break-words">{title}</span>
    </h4>
  );
}

function PercentMeter({ label, value, color }: { label: string; value: number; color: string }) {
  const percent = Math.round(value * 100);
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-start justify-between gap-3 text-sm">
        <span className="min-w-0 break-words">{label}</span>
        <span className="shrink-0 font-semibold tabular-nums">{percent} %</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}%`}
        className="h-2.5 overflow-hidden rounded-full bg-muted/60"
      >
        <div
          aria-hidden="true"
          className={cn('h-full rounded-full', color)}
          style={{ width: `${clampUnit(value) * 100}%` }}
        />
      </div>
    </div>
  );
}
