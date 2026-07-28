/**
 * Scenes of section 05 — "Day to day": customizable briefing grid, starter
 * checklist with its micro-celebration, empty-chat starters, PWA install.
 * Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import { Check, CheckCircle2, Circle, EyeOff, Sparkles } from 'lucide-react';

import { cn } from '@/lib/utils';

import { Cursor, MiniChip, PhoneFrame, SkeletonLine, STAGE } from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type BriefingPhase = 'grid' | 'swap' | 'hide';
const BRIEFING_STEPS: readonly TimelineStep<BriefingPhase>[] = [
  { at: 0, state: 'grid' },
  { at: 1000, state: 'swap' },
  { at: 2300, state: 'hide' },
];

function BriefingCard({ className, dimmed }: { className?: string; dimmed?: boolean }) {
  return (
    <div
      className={cn(
        'relative flex h-10 flex-col justify-center gap-1 rounded-md border border-border bg-background px-2 transition-all duration-500 ease-out',
        dimmed && 'opacity-30',
        className
      )}
    >
      <SkeletonLine w="w-2/3" className="h-1.5" />
      <SkeletonLine w="w-1/3" className="h-1.5" />
      {dimmed && <EyeOff className="absolute right-1 top-1 h-3 w-3 text-muted-foreground" />}
    </div>
  );
}

function BriefingCustomScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(BRIEFING_STEPS, { active });
  const swapped = phase !== 'grid';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="grid w-full max-w-[210px] grid-cols-2 gap-1.5">
        <BriefingCard className={cn(swapped && 'translate-x-[calc(100%+0.375rem)]')} />
        <BriefingCard className={cn(swapped && '-translate-x-[calc(100%+0.375rem)]')} />
        <BriefingCard />
        <BriefingCard dimmed={phase === 'hide'} />
      </div>
    </div>
  );
}

type ChecklistPhase = 'c0' | 'c1' | 'c2' | 'c3' | 'party' | 'done';
const CHECKLIST_STEPS: readonly TimelineStep<ChecklistPhase>[] = [
  { at: 0, state: 'c0' },
  { at: 700, state: 'c1' },
  { at: 1400, state: 'c2' },
  { at: 2100, state: 'c3' },
  { at: 2500, state: 'party' },
  { at: 3400, state: 'done' },
];

const CHECK_DONE_AT: readonly ChecklistPhase[][] = [
  ['c1', 'c2', 'c3', 'party', 'done'],
  ['c2', 'c3', 'party', 'done'],
  ['c3', 'party', 'done'],
];

/** Confetti burst: six dots flying out on phase 'party', gone at 'done'. */
const CONFETTI = [
  '-translate-x-6 -translate-y-5',
  'translate-x-6 -translate-y-6',
  '-translate-x-8 translate-y-1',
  'translate-x-8 -translate-y-1',
  '-translate-x-3 -translate-y-8',
  'translate-x-3 translate-y-4',
] as const;

function StarterChecklistScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(CHECKLIST_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5')}>
      {CHECK_DONE_AT.map((doneAt, i) => {
        const done = doneAt.includes(phase);
        return (
          <div key={i} className="flex w-full max-w-[190px] items-center gap-2">
            {done ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
            ) : (
              <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
            )}
            <SkeletonLine w={i === 1 ? 'w-3/5' : 'w-4/5'} />
          </div>
        );
      })}
      <span className="relative mt-1 flex h-5 items-center justify-center">
        <Sparkles
          className={cn(
            'h-4 w-4 text-primary transition-all duration-300',
            phase === 'party' || phase === 'done' ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
          )}
        />
        {CONFETTI.map((fly, i) => (
          <span
            key={i}
            className={cn(
              'absolute h-1 w-1 rounded-full transition-all duration-700 ease-out',
              i % 2 === 0 ? 'bg-primary' : 'bg-muted-foreground/60',
              phase === 'party' ? cn(fly, 'opacity-100') : 'translate-x-0 translate-y-0 opacity-0'
            )}
          />
        ))}
      </span>
    </div>
  );
}

type StartersPhase = 'empty' | 'chip1' | 'chip2' | 'chip3' | 'hover';
const STARTERS_STEPS: readonly TimelineStep<StartersPhase>[] = [
  { at: 0, state: 'empty' },
  { at: 700, state: 'chip1' },
  { at: 1000, state: 'chip2' },
  { at: 1300, state: 'chip3' },
  { at: 2200, state: 'hover' },
];

const STARTER_VISIBLE_AT: readonly StartersPhase[][] = [
  ['chip1', 'chip2', 'chip3', 'hover'],
  ['chip2', 'chip3', 'hover'],
  ['chip3', 'hover'],
];

function EmptyStartersScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(STARTERS_STEPS, { active });
  const texts = [labels.s1, labels.s2, labels.s3];
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5')}>
      {STARTER_VISIBLE_AT.map((visibleAt, i) => (
        <MiniChip
          key={i}
          pressed={i === 0 && phase === 'hover'}
          className={cn(
            'transition-all duration-300',
            visibleAt.includes(phase) ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0',
            i === 0 && phase === 'hover' && 'scale-105'
          )}
        >
          {texts[i]}
        </MiniChip>
      ))}
      <Cursor
        className={cn(
          phase === 'hover' ? 'left-[62%] top-[32%] opacity-100' : 'left-[70%] top-[80%] opacity-0'
        )}
      />
    </div>
  );
}

type PwaPhase = 'grid' | 'installing' | 'installed' | 'check';
const PWA_STEPS: readonly TimelineStep<PwaPhase>[] = [
  { at: 0, state: 'grid' },
  { at: 900, state: 'installing' },
  { at: 1800, state: 'installed' },
  { at: 2400, state: 'check' },
];

function PwaScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(PWA_STEPS, { active });
  const appIn = phase === 'installed' || phase === 'check';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <PhoneFrame className="h-[7.5rem]">
        <div className="grid grid-cols-3 gap-1 p-0.5">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className="h-3.5 w-3.5 rounded-md bg-muted-foreground/15" />
          ))}
          <span
            className={cn(
              'flex h-3.5 w-3.5 items-center justify-center rounded-md bg-primary/20 transition-all duration-500 ease-out',
              appIn ? 'scale-100 opacity-100' : 'scale-0 opacity-0'
            )}
          >
            <Sparkles className="h-2 w-2 text-primary" />
          </span>
        </div>
      </PhoneFrame>
      <span
        className={cn(
          'absolute right-[30%] top-4 flex h-5 w-5 items-center justify-center rounded-full border border-primary/40 bg-background shadow-sm transition-all duration-300',
          phase === 'check' ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
        )}
      >
        <Check className="h-3 w-3 text-primary" />
      </span>
    </div>
  );
}

export const DAILY_SCENES: Readonly<Record<string, SceneComponent>> = {
  briefing_custom: BriefingCustomScene,
  starter_checklist: StarterChecklistScene,
  empty_starters: EmptyStartersScene,
  pwa: PwaScene,
};
