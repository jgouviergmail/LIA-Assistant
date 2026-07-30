/**
 * Scenes of section 06 — "Unseen but felt": background response continuity,
 * widgets that travel across devices, per-response cost transparency, and
 * the accessibility care (focus ring travelling on Tab). Timer-driven
 * micro-demos; last phase = resting frame.
 */

'use client';

import { Check, Coins, EyeOff, Map as MapIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

import {
  Cursor,
  KeyCap,
  MiniBubble,
  MiniToast,
  PhoneFrame,
  SkeletonLine,
  STAGE,
} from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type BackgroundPhase = 'streaming' | 'away' | 'done' | 'back';
const BACKGROUND_STEPS: readonly TimelineStep<BackgroundPhase>[] = [
  { at: 0, state: 'streaming' },
  { at: 1100, state: 'away' },
  { at: 2300, state: 'done' },
  { at: 3000, state: 'back' },
];

function BackgroundResponseScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(BACKGROUND_STEPS, { active });
  const away = phase === 'away' || phase === 'done';
  const complete = phase === 'done' || phase === 'back';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <div className={cn('transition-opacity duration-500', away && 'opacity-30')}>
        <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
          <SkeletonLine w="w-full" />
          <SkeletonLine w={complete ? 'w-4/5' : 'w-1/3'} className="transition-all duration-500" />
          {!complete && (
            <span className="flex gap-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className={cn(
                    'h-1 w-1 rounded-full bg-muted-foreground/50',
                    active && phase === 'streaming' && 'animate-pulse'
                  )}
                />
              ))}
            </span>
          )}
        </MiniBubble>
      </div>
      <EyeOff
        className={cn(
          'absolute right-5 top-4 h-4 w-4 text-muted-foreground transition-opacity duration-300',
          away ? 'opacity-100' : 'opacity-0'
        )}
      />
      <MiniToast
        icon={Check}
        tone="success"
        className={cn(
          'absolute bottom-3 right-4 transition-all duration-300',
          complete ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        {labels.ready}
      </MiniToast>
    </div>
  );
}

type WidgetsPhase = 'desktop' | 'phone' | 'synced';
const WIDGETS_STEPS: readonly TimelineStep<WidgetsPhase>[] = [
  { at: 0, state: 'desktop' },
  { at: 1100, state: 'phone' },
  { at: 2200, state: 'synced' },
];

function MiniWidget({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex flex-col gap-1 rounded-md border border-border bg-background p-1.5',
        className
      )}
    >
      <MapIcon className="h-3.5 w-3.5 text-primary" />
      <SkeletonLine w="w-full" className="h-1" />
      <SkeletonLine w="w-2/3" className="h-1" />
    </div>
  );
}

function WidgetsTravelScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(WIDGETS_STEPS, { active });
  const phoneIn = phase !== 'desktop';
  return (
    <div className={cn(STAGE, 'flex-row items-center justify-center gap-4')}>
      <MiniWidget className="w-20" />
      <div
        className={cn(
          'transition-all duration-500 ease-out',
          phoneIn ? 'translate-x-0 opacity-100' : 'translate-x-6 opacity-0'
        )}
      >
        <PhoneFrame className="h-24 w-14">
          <MiniWidget className="p-1" />
        </PhoneFrame>
      </div>
      <Check
        className={cn(
          'absolute right-[26%] top-4 h-4 w-4 text-primary transition-all duration-300',
          phase === 'synced' ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
        )}
      />
    </div>
  );
}

type CostPhase = 'bubble' | 'hover' | 'pill';
const COST_STEPS: readonly TimelineStep<CostPhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 1100, state: 'hover' },
  { at: 1800, state: 'pill' },
];

function CostTransparencyScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(COST_STEPS, { active });
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-1.5')}>
      <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
        <SkeletonLine w="w-full" />
        <SkeletonLine w="w-3/5" />
      </MiniBubble>
      <span
        className={cn(
          'flex items-center gap-1.5 self-start rounded-full border border-border bg-background px-2 py-1 transition-all duration-300',
          phase === 'pill' ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <Coins className="h-3 w-3 text-primary" />
        <SkeletonLine w="w-4" className="h-1.5" />
        <SkeletonLine w="w-6" className="h-1.5" />
      </span>
      <Cursor
        className={cn(
          phase === 'bubble'
            ? 'left-[75%] top-[75%] opacity-0'
            : 'left-[45%] top-[45%] opacity-100',
          phase === 'pill' && 'left-[30%] top-[70%]'
        )}
      />
    </div>
  );
}

type A11yPhase = 'f1' | 'f2' | 'f3';
const A11Y_STEPS: readonly TimelineStep<A11yPhase>[] = [
  { at: 0, state: 'f1' },
  { at: 1000, state: 'f2' },
  { at: 2000, state: 'f3' },
];

const FOCUS_ORDER: readonly A11yPhase[] = ['f1', 'f2', 'f3'];

function A11yCareScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(A11Y_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-3')}>
      <div className="flex items-center gap-2">
        {FOCUS_ORDER.map(slot => (
          <span
            key={slot}
            className={cn(
              'flex h-7 w-14 items-center justify-center rounded-md border border-border bg-background transition-shadow duration-300',
              phase === slot && 'ring-2 ring-primary ring-offset-2 ring-offset-background'
            )}
          >
            <SkeletonLine w="w-8" />
          </span>
        ))}
      </div>
      <KeyCap>Tab ⇥</KeyCap>
    </div>
  );
}

type GlassPhase = 'top' | 'scrolled' | 'deep';
const GLASS_STEPS: readonly TimelineStep<GlassPhase>[] = [
  { at: 0, state: 'top' },
  { at: 1200, state: 'scrolled' },
  { at: 2400, state: 'deep' },
];

const GLASS_SCROLL: Readonly<Record<GlassPhase, string>> = {
  top: 'translate-y-0',
  scrolled: '-translate-y-4',
  deep: '-translate-y-9',
};

/**
 * The frosted-glass signature: skeleton content scrolls and genuinely slides
 * BENEATH a translucent blurred header band — the blur is real, not painted.
 */
function FrostedGlassScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(GLASS_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-start overflow-hidden p-0')}>
      <div
        className={cn(
          'flex flex-col gap-2 px-5 pt-10 transition-transform duration-700 ease-out',
          GLASS_SCROLL[phase]
        )}
      >
        <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
          <SkeletonLine w="w-full" />
          <SkeletonLine w="w-1/2" />
        </MiniBubble>
        <MiniBubble side="user" className="w-1/2 space-y-1.5 self-end">
          <SkeletonLine w="w-full" />
        </MiniBubble>
        <MiniBubble side="assistant" className="w-2/3 space-y-1.5">
          <SkeletonLine w="w-full" />
          <SkeletonLine w="w-2/3" />
        </MiniBubble>
      </div>
      <div className="absolute inset-x-0 top-0 flex h-8 items-center gap-2 border-b border-border/40 bg-card/60 px-4 backdrop-blur-md">
        <SkeletonLine w="w-12" className="h-1.5" />
        <span className="ml-auto flex gap-1.5">
          <SkeletonLine w="w-5" className="h-1.5" />
          <SkeletonLine w="w-5" className="h-1.5" />
        </span>
      </div>
    </div>
  );
}

export const UNSEEN_SCENES: Readonly<Record<string, SceneComponent>> = {
  background_response: BackgroundResponseScene,
  widgets_travel: WidgetsTravelScene,
  cost_transparency: CostTransparencyScene,
  a11y_care: A11yCareScene,
  frosted_glass: FrostedGlassScene,
};
