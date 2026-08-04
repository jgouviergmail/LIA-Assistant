/**
 * Scenes of section 06 — "Unseen but felt": background response continuity,
 * widgets that travel across devices, per-response cost transparency, and
 * the accessibility care (focus ring travelling on Tab), and the reflow that
 * keeps a narrow screen readable. Timer-driven micro-demos; last phase =
 * resting frame.
 */

'use client';

import { Check, Coins, EyeOff, Map as MapIcon, Vibrate } from 'lucide-react';

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

type NarrowPhase = 'wide' | 'shrinking' | 'narrow';
const NARROW_STEPS: readonly TimelineStep<NarrowPhase>[] = [
  { at: 0, state: 'wide' },
  { at: 1400, state: 'shrinking' },
  { at: 2200, state: 'narrow' },
];

const NARROW_WIDTH: Readonly<Record<NarrowPhase, string>> = {
  wide: 'w-full',
  shrinking: 'w-2/3',
  narrow: 'w-1/2',
};

/**
 * The narrow-screen promise: as the frame shrinks, a settings row REFLOWS —
 * the label wraps and the action drops beneath it — instead of running past
 * the edge. Resting frame = the narrow layout, which is the point.
 */
function NarrowScreensScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(NARROW_STEPS, { active });
  const narrow = phase === 'narrow';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div
        className={cn(
          'rounded-lg border border-border/60 bg-card/70 p-2 transition-all duration-700 ease-out',
          NARROW_WIDTH[phase]
        )}
      >
        <div className={cn('flex gap-2', narrow ? 'flex-col items-start' : 'items-center')}>
          <div className="min-w-0 flex-1 space-y-1">
            <SkeletonLine w="w-full" className="h-1.5" />
            <SkeletonLine w={narrow ? 'w-4/5' : 'w-1/2'} className="h-1.5" />
          </div>
          <span
            className={cn(
              'shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[9px] font-medium text-primary transition-all duration-500',
              narrow && 'self-start'
            )}
          >
            <SkeletonLine w="w-6" className="h-1 bg-primary/40" />
          </span>
        </div>
      </div>
      <span className="mt-2 flex items-center gap-1 text-[9px] text-muted-foreground">
        <Check className="h-2.5 w-2.5 text-emerald-500" aria-hidden="true" />
        <SkeletonLine w="w-10" className="h-1" />
      </span>
    </div>
  );
}


/**
 * Haptics — a brief tap, on request.
 *
 * The ring expands once and fades: a buzz longer than a few tens of
 * milliseconds reads as an alarm, not as an acknowledgement, and the scene
 * says so by never lingering. `motion-reduce` neutralises the pulse — the
 * page must not animate at someone who asked it not to.
 */
type HapticPhase = 'idle' | 'tap' | 'echo' | 'rest';
const HAPTIC_STEPS: readonly TimelineStep<HapticPhase>[] = [
  { at: 0, state: 'idle' },
  { at: 900, state: 'tap' },
  { at: 1150, state: 'echo' },
  { at: 2200, state: 'rest' },
];

function HapticsScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(HAPTIC_STEPS, { active });
  const firing = phase === 'tap' || phase === 'echo';
  return (
    <div className={cn(STAGE, 'items-center justify-center')}>
      <PhoneFrame className="relative flex items-center justify-center">
        <span
          aria-hidden="true"
          className={cn(
            'absolute h-10 w-10 rounded-full border-2 border-primary/60 transition-all duration-300 motion-reduce:transition-none',
            phase === 'tap' && 'scale-100 opacity-90',
            phase === 'echo' && 'scale-150 opacity-0',
            (phase === 'idle' || phase === 'rest') && 'scale-75 opacity-0'
          )}
        />
        <span
          className={cn(
            'relative flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background transition-transform duration-150 motion-reduce:transition-none',
            firing && 'scale-105'
          )}
        >
          <Vibrate className={cn('h-4 w-4', firing ? 'text-primary' : 'text-muted-foreground')} />
        </span>
      </PhoneFrame>
    </div>
  );
}

type SkyPhase = 'dark' | 'lighting' | 'traced';
const SKY_STEPS: readonly TimelineStep<SkyPhase>[] = [
  { at: 0, state: 'dark' },
  { at: 700, state: 'lighting' },
  { at: 1900, state: 'traced' },
];

/** Where the stars sit, and which of them are lit — fixed, like the real map. */
const SKY_STARS = [
  { x: 50, y: 16, lit: true },
  { x: 80, y: 38, lit: true },
  { x: 72, y: 74, lit: false },
  { x: 28, y: 74, lit: true },
  { x: 20, y: 38, lit: true },
] as const;
const LIT_FIGURE = SKY_STARS.filter(star => star.lit)
  .map(star => `${star.x},${star.y}`)
  .join(' ');

/**
 * The capability constellation: stars resolve in order, then the figure draws
 * itself between the lit ones. Same idea as the real chart, at postcard size.
 */
function CapabilityMapScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(SKY_STEPS, { active });

  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="relative aspect-square w-full max-w-[150px] overflow-hidden rounded-xl border border-border bg-[radial-gradient(circle_at_50%_45%,var(--capability-glow-blue),transparent_65%)]">
        <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <circle
            cx="50"
            cy="50"
            r="34"
            fill="none"
            stroke="var(--capability-star)"
            strokeOpacity="0.15"
            strokeWidth="0.4"
            strokeDasharray="1.5 2.5"
          />
          <polygon
            points={LIT_FIGURE}
            fill="var(--capability-star)"
            fillOpacity={phase === 'traced' ? 0.08 : 0}
            stroke="var(--capability-accent)"
            strokeWidth="1"
            strokeLinejoin="round"
            pathLength={100}
            strokeDasharray="100"
            strokeDashoffset={phase === 'traced' ? 0 : 100}
            className="transition-all duration-[1200ms] ease-out"
          />
          {SKY_STARS.map((star, index) => (
            <circle
              key={index}
              cx={star.x}
              cy={star.y}
              r={star.lit ? 3 : 2}
              fill={star.lit ? 'var(--capability-star)' : 'none'}
              stroke={star.lit ? 'none' : 'var(--capability-ink-dim)'}
              strokeWidth="0.8"
              className="transition-opacity duration-500"
              style={{
                opacity: phase === 'dark' ? 0.15 : 1,
                transitionDelay: `${index * 120}ms`,
              }}
            />
          ))}
          <circle cx="50" cy="50" r="2" fill="var(--capability-star)" fillOpacity="0.9" />
        </svg>
      </div>
    </div>
  );
}

type GlancePhase = 'flat' | 'ranked';
const GLANCE_STEPS: readonly TimelineStep<GlancePhase>[] = [
  { at: 0, state: 'flat' },
  { at: 1400, state: 'ranked' },
];

/**
 * Three status pills that start as one pale wash and separate by DENSITY —
 * the same move the app makes: a filled ground for the urgent one, a tint for
 * the middle, neutral for the rest.
 */
function ReadableAtAGlanceScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(GLANCE_STEPS, { active });
  const ranked = phase === 'ranked';

  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[190px] space-y-2">
        {[
          {
            key: 'high',
            width: 'w-4/5',
            flat: 'bg-destructive/10 text-destructive border-destructive/20',
            lit: 'bg-destructive text-destructive-foreground border-destructive',
          },
          {
            key: 'medium',
            width: 'w-3/5',
            flat: 'bg-destructive/10 text-destructive border-destructive/20',
            lit: 'bg-warning/10 text-warning border-warning/20',
          },
          {
            key: 'low',
            width: 'w-2/5',
            flat: 'bg-destructive/10 text-destructive border-destructive/20',
            lit: 'bg-secondary text-secondary-foreground border-border',
          },
        ].map(row => (
          <div key={row.key} className="flex items-center gap-2">
            <span
              className={cn(
                'h-3 w-8 shrink-0 rounded-full border transition-colors duration-700',
                ranked ? row.lit : row.flat
              )}
            />
            <SkeletonLine w={row.width} />
          </div>
        ))}
      </div>
    </div>
  );
}

export const UNSEEN_SCENES: Readonly<Record<string, SceneComponent>> = {
  readable_at_a_glance: ReadableAtAGlanceScene,
  capability_map: CapabilityMapScene,
  background_response: BackgroundResponseScene,
  widgets_travel: WidgetsTravelScene,
  cost_transparency: CostTransparencyScene,
  haptics: HapticsScene,
  a11y_care: A11yCareScene,
  frosted_glass: FrostedGlassScene,
  narrow_screens: NarrowScreensScene,
};
