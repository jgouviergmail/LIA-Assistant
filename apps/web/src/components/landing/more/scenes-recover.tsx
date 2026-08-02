/**
 * Scenes of section 03 — "When things go wrong": actionable errors, one-click
 * retry, early quota warning, image expiry notice, named attachment limits,
 * correcting a commitment the extractor misheard.
 * Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import {
  AlertTriangle,
  Bell,
  Check,
  Clock,
  FileWarning,
  Image as ImageIcon,
  PencilLine,
  RefreshCw,
  RotateCcw,
  RotateCw,
} from 'lucide-react';

import { cn } from '@/lib/utils';

import {
  Cursor,
  MiniBubble,
  MiniChip,
  MiniGauge,
  MiniToast,
  SkeletonLine,
  STAGE,
} from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type ErrorPhase = 'error' | 'action' | 'pulse' | 'settle';
const ERROR_STEPS: readonly TimelineStep<ErrorPhase>[] = [
  { at: 0, state: 'error' },
  { at: 1000, state: 'action' },
  { at: 2000, state: 'pulse' },
  { at: 2600, state: 'settle' },
];

function ActionableErrorsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(ERROR_STEPS, { active });
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <MiniBubble side="assistant" tone="destructive" className="w-4/5">
        <span className="flex items-center gap-1.5 text-destructive">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span className="truncate font-medium">{labels.cause}</span>
        </span>
      </MiniBubble>
      <MiniChip
        pressed
        className={cn(
          'self-start transition-all duration-300',
          phase === 'error' ? 'translate-y-1 opacity-0' : 'translate-y-0 opacity-100',
          phase === 'pulse' && 'scale-110'
        )}
      >
        {labels.action}
      </MiniChip>
    </div>
  );
}

type RetryPhase = 'failed' | 'clicked' | 'spinning' | 'success';
const RETRY_STEPS: readonly TimelineStep<RetryPhase>[] = [
  { at: 0, state: 'failed' },
  { at: 1100, state: 'clicked' },
  { at: 1500, state: 'spinning' },
  { at: 2600, state: 'success' },
];

function RetryTurnScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(RETRY_STEPS, { active });
  const failed = phase === 'failed' || phase === 'clicked';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <MiniBubble
        side="assistant"
        tone={phase === 'success' ? 'success' : 'destructive'}
        className="w-3/4"
      >
        <span className="flex items-center gap-1.5">
          {phase === 'success' ? (
            <Check className="h-3 w-3 shrink-0 text-primary" />
          ) : (
            <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" />
          )}
          <SkeletonLine w="w-24" />
        </span>
      </MiniBubble>
      <span
        className={cn(
          'flex h-6 w-6 items-center justify-center self-start rounded-full border border-border bg-background transition-all duration-300',
          phase === 'clicked' && 'scale-90 border-primary/60',
          phase === 'success' && 'opacity-0'
        )}
      >
        {phase === 'spinning' ? (
          <RotateCw className={cn('h-3 w-3 text-primary', active && 'animate-spin')} />
        ) : (
          <RotateCcw className="h-3 w-3 text-muted-foreground" />
        )}
      </span>
      <Cursor
        className={cn(
          failed ? 'left-[15%] bottom-[22%] opacity-100' : 'left-[15%] bottom-[22%] opacity-0',
          phase === 'failed' && 'left-[40%] bottom-[10%]'
        )}
      />
    </div>
  );
}

type QuotaPhase = 'empty' | 'filling' | 'warned';
const QUOTA_STEPS: readonly TimelineStep<QuotaPhase>[] = [
  { at: 0, state: 'empty' },
  { at: 500, state: 'filling' },
  { at: 1700, state: 'warned' },
];

function QuotaWarningScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(QUOTA_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-3')}>
      <div className="w-full max-w-[200px]">
        <MiniGauge
          pct={phase === 'empty' ? 8 : 78}
          tone={phase === 'warned' ? 'warning' : 'default'}
        />
      </div>
      <MiniToast
        icon={Bell}
        tone="warning"
        className={cn(
          'transition-all duration-300',
          phase === 'warned' ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        {labels.warned}
      </MiniToast>
    </div>
  );
}

type ExpiryPhase = 'img' | 'badge' | 'pulse' | 'settle';
const EXPIRY_STEPS: readonly TimelineStep<ExpiryPhase>[] = [
  { at: 0, state: 'img' },
  { at: 1100, state: 'badge' },
  { at: 2100, state: 'pulse' },
  { at: 2700, state: 'settle' },
];

function ImageExpiryScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(EXPIRY_STEPS, { active });
  const badgeIn = phase !== 'img';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="relative">
        <div className="flex h-20 w-28 items-center justify-center rounded-lg border border-border bg-background">
          <ImageIcon className="h-6 w-6 text-muted-foreground/50" />
        </div>
        <span
          className={cn(
            'absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full border border-warning/40 bg-background shadow-sm transition-all duration-300',
            badgeIn ? 'scale-100 opacity-100' : 'scale-50 opacity-0',
            phase === 'pulse' && 'scale-125'
          )}
        >
          <Clock className="h-3 w-3 text-warning" />
        </span>
        <SkeletonLine w="w-20" className="mt-2" />
      </div>
    </div>
  );
}

type LimitPhase = 'chip' | 'shakeL' | 'shakeR' | 'toast';
const LIMIT_STEPS: readonly TimelineStep<LimitPhase>[] = [
  { at: 0, state: 'chip' },
  { at: 1000, state: 'shakeL' },
  { at: 1150, state: 'shakeR' },
  { at: 1500, state: 'toast' },
];

function AttachmentLimitsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(LIMIT_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-3')}>
      <span
        className={cn(
          'flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 transition-transform duration-150',
          phase === 'shakeL' && '-translate-x-1',
          phase === 'shakeR' && 'translate-x-1',
          phase === 'toast' && 'opacity-60'
        )}
      >
        <FileWarning className="h-3 w-3 text-muted-foreground" />
        <SkeletonLine w="w-12" />
      </span>
      <MiniToast
        icon={AlertTriangle}
        tone="warning"
        className={cn(
          'transition-all duration-300',
          phase === 'toast' ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        {labels.limit}
      </MiniToast>
    </div>
  );
}

type FreshPhase = 'fresh' | 'stale' | 'retry' | 'refreshed';
const FRESH_STEPS: readonly TimelineStep<FreshPhase>[] = [
  { at: 0, state: 'fresh' },
  { at: 1000, state: 'stale' },
  { at: 2000, state: 'retry' },
  { at: 2800, state: 'refreshed' },
];

function HonestFreshnessScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(FRESH_STEPS, { active });
  const stale = phase === 'stale' || phase === 'retry';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-2 rounded-lg border border-border bg-background p-2.5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <SkeletonLine w="w-1/3" />
          <span
            className={cn(
              'flex items-center gap-1 text-[9px] font-medium transition-colors duration-300',
              stale ? 'text-warning' : 'text-muted-foreground'
            )}
          >
            <Clock className="h-2.5 w-2.5" />
            {labels.fresh}
          </span>
        </div>
        <SkeletonLine
          w="w-full"
          className={cn('transition-opacity duration-300', stale && 'opacity-30')}
        />
        <SkeletonLine
          w="w-4/5"
          className={cn('transition-opacity duration-300', stale && 'opacity-30')}
        />
        <span
          className={cn(
            'flex w-fit items-center gap-1 rounded-md border px-2 py-1 text-[9px] transition-all duration-300',
            stale ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0',
            phase === 'retry'
              ? 'border-primary/60 text-primary ring-2 ring-primary/30'
              : 'border-border text-muted-foreground'
          )}
        >
          <RefreshCw className={cn('h-2.5 w-2.5', phase === 'retry' && active && 'animate-spin')} />
          {labels.retry}
        </span>
      </div>
      <Cursor
        className={cn(
          phase === 'retry'
            ? 'left-[24%] bottom-[26%] opacity-100'
            : 'left-[60%] bottom-[12%] opacity-0'
        )}
      />
    </div>
  );
}

type FixPhase = 'wrong' | 'editing' | 'fixed' | 'settle';
const FIX_STEPS: readonly TimelineStep<FixPhase>[] = [
  { at: 0, state: 'wrong' },
  { at: 1200, state: 'editing' },
  { at: 2200, state: 'fixed' },
  { at: 3200, state: 'settle' },
];

function FixCommitmentScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(FIX_STEPS, { active });
  const corrected = phase === 'fixed' || phase === 'settle';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <div className="flex items-center gap-2 rounded-md border border-border/60 bg-background/70 px-2 py-1.5">
        {/* The strike-through alone marks the superseded wording. Dimming it on
            top dropped the contrast to 2.65:1 in dark mode — an axe serious
            violation, and a line nobody could read anyway. */}
        <span
          className={cn(
            'min-w-0 flex-1 truncate text-[10px] text-muted-foreground transition-all duration-300',
            corrected && 'line-through'
          )}
        >
          {labels.before}
        </span>
        <PencilLine
          className={cn(
            'h-3 w-3 shrink-0 transition-colors duration-300',
            phase === 'editing' ? 'text-primary' : 'text-muted-foreground'
          )}
        />
      </div>
      <div
        className={cn(
          'flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-2 py-1.5 transition-all duration-300',
          corrected ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <Check className="h-3 w-3 shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">{labels.after}</span>
      </div>
    </div>
  );
}

export const RECOVER_SCENES: Readonly<Record<string, SceneComponent>> = {
  actionable_errors: ActionableErrorsScene,
  retry_turn: RetryTurnScene,
  honest_freshness: HonestFreshnessScene,
  quota_warning: QuotaWarningScene,
  image_expiry: ImageExpiryScene,
  attachment_limits: AttachmentLimitsScene,
  fix_commitment: FixCommitmentScene,
};
