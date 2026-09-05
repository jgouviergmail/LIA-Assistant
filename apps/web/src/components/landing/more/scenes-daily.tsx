/**
 * Scenes of section 05 — "Day to day": customizable briefing grid, starter
 * checklist with its micro-celebration, empty-chat starters, PWA install.
 * Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import {
  Star,
  MessageSquare,
  CalendarClock,
  Bell,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  EyeOff,
  FileText,
  Sparkles,
  LifeBuoy,
} from 'lucide-react';

import { cn } from '@/lib/utils';

import { Cursor, MiniChip, MiniSettingRow, PhoneFrame, SkeletonLine, STAGE } from './primitives';
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

type EscapePhase = 'unreachable' | 'press' | 'field' | 'typed';
const ESCAPE_STEPS: readonly TimelineStep<EscapePhase>[] = [
  { at: 0, state: 'unreachable' },
  { at: 1300, state: 'press' },
  { at: 1800, state: 'field' },
  { at: 2900, state: 'typed' },
];

/**
 * The native shells' escape hatch: a server address typed wrong on first
 * launch used to mean reinstalling the app — the offline screen now offers a
 * way OUT. The scene plays the rescue: an unreachable address, the lifebuoy
 * pressed, a fresh field, a new address taking shape.
 */
function ServerEscapeHatchScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(ESCAPE_STEPS, { active });
  const rescued = phase === 'field' || phase === 'typed';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <PhoneFrame className="h-[7.5rem]">
        <div className="flex flex-col items-center gap-1.5 p-1 pt-2.5">
          <span
            className={cn(
              'flex h-4 w-16 items-center justify-center gap-1 rounded border px-1 transition-all duration-300',
              rescued
                ? 'border-primary/40 bg-primary/10'
                : 'border-destructive/40 bg-destructive/10'
            )}
          >
            {rescued ? (
              <span
                className={cn(
                  'h-1 rounded-full bg-primary/60 transition-all duration-700 ease-out',
                  phase === 'typed' ? 'w-10' : 'w-1'
                )}
              />
            ) : (
              <span className="w-12 truncate text-[7px] leading-none text-destructive line-through">
                https://oops.
              </span>
            )}
          </span>
          <span
            className={cn(
              'flex h-5 w-5 items-center justify-center rounded-full border bg-background shadow-sm transition-all duration-300',
              phase === 'press'
                ? 'scale-110 border-primary text-primary'
                : 'scale-100 border-border text-muted-foreground',
              rescued && 'opacity-40'
            )}
          >
            <LifeBuoy className="h-3 w-3" />
          </span>
        </div>
      </PhoneFrame>
    </div>
  );
}

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

type CardActPhase = 'card' | 'chips' | 'hover' | 'picked';
const CARDACT_STEPS: readonly TimelineStep<CardActPhase>[] = [
  { at: 0, state: 'card' },
  { at: 800, state: 'chips' },
  { at: 1800, state: 'hover' },
  { at: 2700, state: 'picked' },
];

function CardActionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(CARDACT_STEPS, { active });
  const chipsIn = phase !== 'card';
  const picked = phase === 'picked';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-2 rounded-lg border border-border bg-background p-2.5 shadow-sm">
        <div className="flex items-center gap-2">
          <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
          <SkeletonLine w="w-2/3" />
        </div>
        <div
          className={cn(
            'flex items-center gap-1.5 transition-all duration-300',
            chipsIn ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
          )}
        >
          <MiniChip pressed={phase === 'hover' || picked}>
            {picked && <Check className="h-2.5 w-2.5" />}
            {labels.chip1}
          </MiniChip>
          <MiniChip>{labels.chip2}</MiniChip>
        </div>
      </div>
      <Cursor
        className={cn(
          phase === 'hover' ? 'left-[32%] top-[64%] opacity-100' : 'left-[70%] top-[82%] opacity-0',
          picked && 'opacity-0'
        )}
      />
    </div>
  );
}

/**
 * Folded settings — the panel is an index you open, not a wall you scroll.
 *
 * Three shut rows; one opens and reveals its content. The badge on the closed
 * row is the point: folding must not hide a decision, so what was refused
 * stays legible while everything is shut.
 */
type FoldPhase = 'shut' | 'hover' | 'open' | 'rest';
const FOLD_STEPS: readonly TimelineStep<FoldPhase>[] = [
  { at: 0, state: 'shut' },
  { at: 800, state: 'hover' },
  { at: 1300, state: 'open' },
  { at: 2600, state: 'rest' },
];

function FoldedSettingsScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(FOLD_STEPS, { active });
  const opened = phase === 'open' || phase === 'rest';
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5 px-6')}>
      {[0, 1, 2].map(row => (
        <div key={row} className="w-full">
          <div
            className={cn(
              'flex w-full items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 transition-shadow duration-200 motion-reduce:transition-none',
              row === 1 && phase === 'hover' && 'ring-2 ring-primary/50'
            )}
          >
            <ChevronDown
              className={cn(
                'h-3 w-3 shrink-0 text-muted-foreground transition-transform duration-300 motion-reduce:transition-none',
                row === 1 && opened && 'rotate-180'
              )}
            />
            <SkeletonLine w="w-1/3" />
            {/* Refused-source count: the one thing that must stay readable
                while the block is shut. */}
            {row === 1 && (
              <span className="ml-auto rounded-full bg-muted px-1.5 text-[9px] tabular-nums text-muted-foreground">
                2
              </span>
            )}
          </div>
          {row === 1 && (
            <div
              className={cn(
                'grid overflow-hidden transition-[grid-template-rows] duration-300 motion-reduce:transition-none',
                opened ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
              )}
            >
              <div className="min-h-0">
                <div className="mt-1 space-y-1 pl-5">
                  <SkeletonLine w="w-2/3" />
                  <SkeletonLine w="w-1/2" />
                </div>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

type AlertsPhase = 'folded' | 'hover' | 'open';
const ALERTS_STEPS: readonly TimelineStep<AlertsPhase>[] = [
  { at: 0, state: 'folded' },
  { at: 1100, state: 'hover' },
  { at: 1700, state: 'open' },
];

/** Five folded streams; one opens, and only that one loads. */
function AlertsHubScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(ALERTS_STEPS, { active });
  const rows = [MessageSquare, Sparkles, Star, Bell, CalendarClock];

  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-1">
        {rows.map((Icon, index) => (
          <div key={index} className="space-y-1">
            <MiniSettingRow icon={Icon} highlighted={index === 1 && phase !== 'folded'} />
            {index === 1 && (
              <div
                className={cn(
                  'ml-3 space-y-1 overflow-hidden transition-all duration-500 ease-out',
                  phase === 'open' ? 'max-h-12 opacity-100' : 'max-h-0 opacity-0'
                )}
              >
                <SkeletonLine w="w-4/5" />
                <SkeletonLine w="w-3/5" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

type WeekPhase = 'plan' | 'ran' | 'failed' | 'waiting' | 'monday';
const WEEK_STEPS: readonly TimelineStep<WeekPhase>[] = [
  { at: 0, state: 'plan' },
  { at: 900, state: 'ran' },
  { at: 1800, state: 'failed' },
  { at: 2700, state: 'waiting' },
  { at: 3900, state: 'monday' },
];

/** The chips of the week grid: (column, row, rank) — the rank follows the hour. */
const WEEK_CHIPS = [
  { col: 4, row: 0, rank: 1, id: 'a-fri' },
  { col: 0, row: 1, rank: 2, id: 'b-mon' },
  { col: 2, row: 1, rank: 2, id: 'b-wed' },
  { col: 1, row: 2, rank: 3, id: 'c-tue' },
] as const;

/** What each cell says in each phase: the outcome of the LAST run of its slot. */
const WEEK_TONE: Record<string, Partial<Record<WeekPhase, 'ran' | 'failed' | 'waiting'>>> = {
  'b-mon': { ran: 'ran', failed: 'ran', waiting: 'ran' },
  'c-tue': { failed: 'failed', waiting: 'failed' },
  'b-wed': { waiting: 'waiting' },
};

const WEEK_TONE_CLASS = {
  ran: 'border-success bg-success text-success-foreground',
  failed: 'border-destructive bg-destructive text-destructive-foreground',
  waiting: 'border-warning bg-warning text-warning-foreground',
} as const;

/** Hours down, days across; the cells colour as the week unfolds and blank on Monday. */
function WeekGridScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(WEEK_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[220px]">
        <div className="mb-1 grid grid-cols-[1.25rem_repeat(7,1fr)] gap-x-0.5">
          <span />
          {Array.from({ length: 7 }, (_, day) => (
            <SkeletonLine
              key={day}
              w="w-3/4"
              className={cn('mx-auto h-1.5', day === 2 && 'bg-primary/50')}
            />
          ))}
        </div>
        {Array.from({ length: 3 }, (_, row) => (
          <div key={row} className="grid grid-cols-[1.25rem_repeat(7,1fr)] gap-x-0.5">
            <SkeletonLine w="w-3/4" className="my-auto h-1.5" />
            {Array.from({ length: 7 }, (_, col) => {
              const chip = WEEK_CHIPS.find(c => c.col === col && c.row === row);
              const tone = chip ? WEEK_TONE[chip.id]?.[phase] : undefined;
              return (
                <div
                  key={col}
                  className={cn(
                    'flex h-6 items-center justify-center border-l border-t border-border/50',
                    col === 2 && 'bg-primary/5'
                  )}
                >
                  {chip && (
                    <span
                      className={cn(
                        'inline-flex h-4 min-w-4 items-center justify-center rounded-full border px-1 text-[9px] font-semibold tabular-nums transition-colors duration-500',
                        tone ? WEEK_TONE_CLASS[tone] : 'border-border bg-background text-foreground'
                      )}
                    >
                      {chip.rank}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export const DAILY_SCENES: Readonly<Record<string, SceneComponent>> = {
  alerts_hub: AlertsHubScene,
  briefing_custom: BriefingCustomScene,
  card_actions: CardActionsScene,
  folded_settings: FoldedSettingsScene,
  week_grid: WeekGridScene,
  starter_checklist: StarterChecklistScene,
  empty_starters: EmptyStartersScene,
  pwa: PwaScene,
  server_escape_hatch: ServerEscapeHatchScene,
};
