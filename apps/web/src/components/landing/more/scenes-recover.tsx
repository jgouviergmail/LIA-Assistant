/**
 * Scenes of section 03 — "When things go wrong": actionable errors, one-click
 * retry, early quota warning, image expiry notice, named attachment limits.
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

export const RECOVER_SCENES: Readonly<Record<string, SceneComponent>> = {
  actionable_errors: ActionableErrorsScene,
  retry_turn: RetryTurnScene,
  quota_warning: QuotaWarningScene,
  image_expiry: ImageExpiryScene,
  attachment_limits: AttachmentLimitsScene,
};
