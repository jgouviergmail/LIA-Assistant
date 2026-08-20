/**
 * Scenes of section 02 — "When LIA replies": follow-up chips, the floating
 * return-to-bottom button, the per-bubble action row, share/export, and the
 * execution-trace backstage. Timer-driven micro-demos; last phase = resting
 * frame.
 */

'use client';

import { Trash2, HelpCircle, ChevronDown,
  ArrowDown,
  Check,
  ChevronRight,
  Copy,
  Download,
  FileText,
  Handshake,
  Languages,
  Link2,
  Reply,
  Search,
  Share2,
  ShieldOff,
  TextSelect,
  ThumbsDown,
  ThumbsUp,
  Wrench,
} from 'lucide-react';

import { cn } from '@/lib/utils';

import { Cursor, MiniBubble, MiniChip, MiniToast, SkeletonLine, STAGE } from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type ChipsPhase = 'bubble' | 'chips' | 'hover' | 'picked';
const CHIPS_STEPS: readonly TimelineStep<ChipsPhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 800, state: 'chips' },
  { at: 1800, state: 'hover' },
  { at: 2600, state: 'picked' },
];

function FollowupChipsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(CHIPS_STEPS, { active });
  const chipsIn = phase !== 'bubble';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
        <SkeletonLine w="w-full" />
        <SkeletonLine w="w-2/3" />
      </MiniBubble>
      <div
        className={cn(
          'flex gap-1.5 self-start transition-all duration-300',
          chipsIn ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <MiniChip pressed={phase === 'hover' || phase === 'picked'}>{labels.chip1}</MiniChip>
        <MiniChip>{labels.chip2}</MiniChip>
      </div>
      <MiniBubble
        side="user"
        className={cn(
          'transition-all duration-300',
          phase === 'picked' ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        {labels.chip1}
      </MiniBubble>
      <Cursor
        className={cn(
          phase === 'hover' || phase === 'picked'
            ? 'left-[38%] top-[55%] opacity-100'
            : 'left-[70%] top-[80%] opacity-0'
        )}
      />
    </div>
  );
}

type ScrollPhase = 'reading' | 'newmsg' | 'clicked';
const SCROLL_STEPS: readonly TimelineStep<ScrollPhase>[] = [
  { at: 0, state: 'reading' },
  { at: 900, state: 'newmsg' },
  { at: 2300, state: 'clicked' },
];

function ScrollReturnScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(SCROLL_STEPS, { active });
  return (
    <div className={cn(STAGE, 'items-stretch justify-end gap-2 overflow-hidden')}>
      <div
        className={cn(
          'flex flex-col gap-2 transition-transform duration-500 ease-out',
          phase === 'clicked' ? 'translate-y-0' : '-translate-y-8'
        )}
      >
        <MiniBubble side="user" className="self-end">
          <SkeletonLine w="w-12" className="bg-primary/25" />
        </MiniBubble>
        <MiniBubble side="assistant" className="w-2/3 space-y-1.5">
          <SkeletonLine w="w-full" />
          <SkeletonLine w="w-1/2" />
        </MiniBubble>
      </div>
      <span
        className={cn(
          'absolute bottom-3 right-4 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background shadow-sm transition-all duration-300',
          phase === 'newmsg' ? 'scale-100 opacity-100' : 'scale-75 opacity-0'
        )}
      >
        <ArrowDown className="h-3.5 w-3.5 text-foreground/80" />
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-primary" />
      </span>
      <Cursor
        className={cn(
          phase === 'reading' ? 'right-10 bottom-10 opacity-0' : 'right-5 bottom-4 opacity-100',
          phase === 'clicked' && 'opacity-0'
        )}
      />
    </div>
  );
}

type ActionsPhase = 'bubble' | 'row' | 'copied';
const ACTIONS_STEPS: readonly TimelineStep<ActionsPhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 800, state: 'row' },
  { at: 2000, state: 'copied' },
];

function BubbleActionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(ACTIONS_STEPS, { active });
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-1.5')}>
      <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
        <SkeletonLine w="w-full" />
        <SkeletonLine w="w-3/5" />
      </MiniBubble>
      <div
        className={cn(
          'flex items-center gap-2.5 self-start pl-2 text-muted-foreground transition-all duration-300',
          phase === 'bubble' ? 'translate-y-1 opacity-0' : 'translate-y-0 opacity-100'
        )}
      >
        {phase === 'copied' ? (
          <Check className="h-3 w-3 text-primary" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
        <ThumbsUp className="h-3 w-3" />
        <ThumbsDown className="h-3 w-3" />
      </div>
      <MiniToast
        icon={Check}
        tone="success"
        className={cn(
          'absolute right-4 top-4 transition-all duration-300',
          phase === 'copied' ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0'
        )}
      >
        {labels.copied}
      </MiniToast>
    </div>
  );
}

type SharePhase = 'bubble' | 'm1' | 'm2' | 'm3';
const SHARE_STEPS: readonly TimelineStep<SharePhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 1000, state: 'm1' },
  { at: 1350, state: 'm2' },
  { at: 1700, state: 'm3' },
];

const SHARE_ROWS = [
  { icon: Share2, visibleFrom: ['m1', 'm2', 'm3'] },
  { icon: Download, visibleFrom: ['m2', 'm3'] },
  { icon: Link2, visibleFrom: ['m3'] },
] as const;

function ShareExportScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(SHARE_STEPS, { active });
  return (
    <div className={cn(STAGE, 'flex-row items-center justify-center gap-3')}>
      <MiniBubble side="assistant" className="w-2/5 space-y-1.5">
        <SkeletonLine w="w-full" />
        <SkeletonLine w="w-2/3" />
        <span className="mt-1 flex items-center gap-2 text-muted-foreground">
          <Share2 className={cn('h-3 w-3', phase !== 'bubble' && 'text-primary')} />
          <SkeletonLine w="w-6" />
        </span>
      </MiniBubble>
      <div className="w-2/5 space-y-1">
        {SHARE_ROWS.map(({ icon: Icon, visibleFrom }, i) => (
          <div
            key={i}
            className={cn(
              'flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5 transition-all duration-300',
              (visibleFrom as readonly string[]).includes(phase)
                ? 'translate-x-0 opacity-100'
                : 'translate-x-2 opacity-0'
            )}
          >
            <Icon className="h-3 w-3 text-muted-foreground" />
            <SkeletonLine w="w-3/5" />
          </div>
        ))}
      </div>
    </div>
  );
}

type BackstagePhase = 'closed' | 'open' | 's1' | 's2' | 's3';
const BACKSTAGE_STEPS: readonly TimelineStep<BackstagePhase>[] = [
  { at: 0, state: 'closed' },
  { at: 900, state: 'open' },
  { at: 1500, state: 's1' },
  { at: 2100, state: 's2' },
  { at: 2700, state: 's3' },
];

const BACKSTAGE_ROWS = [
  { icon: Search, doneFrom: ['s1', 's2', 's3'] },
  { icon: Wrench, doneFrom: ['s2', 's3'] },
  { icon: FileText, doneFrom: ['s3'] },
] as const;

function BackstageScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(BACKSTAGE_STEPS, { active });
  const open = phase !== 'closed';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-1.5')}>
      <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
        <SkeletonLine w="w-full" />
      </MiniBubble>
      <div className="flex items-center gap-1 self-start pl-2 text-muted-foreground">
        <ChevronRight
          className={cn('h-3 w-3 transition-transform duration-300', open && 'rotate-90')}
        />
        <SkeletonLine w="w-10" />
      </div>
      <div
        className={cn(
          'space-y-1 self-start pl-6 transition-all duration-300',
          open ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0'
        )}
      >
        {BACKSTAGE_ROWS.map(({ icon: Icon, doneFrom }, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <Icon className="h-3 w-3 text-muted-foreground" />
            <SkeletonLine w="w-16" />
            <Check
              className={cn(
                'h-3 w-3 transition-all duration-300',
                (doneFrom as readonly string[]).includes(phase)
                  ? 'scale-100 text-primary opacity-100'
                  : 'scale-50 opacity-0'
              )}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

type SelectPhase = 'bubble' | 'selected' | 'bar' | 'picked';
const SELECT_STEPS: readonly TimelineStep<SelectPhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 800, state: 'selected' },
  { at: 1700, state: 'bar' },
  { at: 2700, state: 'picked' },
];

function SelectionActionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(SELECT_STEPS, { active });
  const selected = phase !== 'bubble';
  const barIn = phase === 'bar' || phase === 'picked';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2.5')}>
      <MiniBubble side="assistant" className="w-3/4 space-y-1.5">
        <SkeletonLine w="w-full" />
        <div
          className={cn(
            'h-2 w-1/2 rounded-full transition-colors duration-300',
            selected ? 'bg-primary/30' : 'bg-muted-foreground/15'
          )}
        />
      </MiniBubble>
      <div
        className={cn(
          'flex items-center gap-2 self-center rounded-lg border border-border bg-background px-2 py-1.5 shadow-sm transition-all duration-300',
          barIn ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <TextSelect className="h-3 w-3 text-muted-foreground" />
        <MiniChip pressed={phase === 'picked'}>{labels.action}</MiniChip>
        <Languages className="h-3 w-3 text-muted-foreground" />
      </div>
      <Cursor
        className={cn(
          barIn && phase !== 'picked'
            ? 'left-[43%] top-[64%] opacity-100'
            : 'left-[68%] top-[38%] opacity-0'
        )}
      />
    </div>
  );
}

type PeerPhase = 'bubble' | 'actions' | 'reply' | 'prefilled';
const PEER_STEPS: readonly TimelineStep<PeerPhase>[] = [
  { at: 0, state: 'bubble' },
  { at: 900, state: 'actions' },
  { at: 1900, state: 'reply' },
  { at: 2600, state: 'prefilled' },
];

/**
 * A relayed peer message lands in its tinted bubble; Reply/Block quick
 * actions appear beneath it, Reply is picked, and the composer prefills —
 * nothing sends by itself.
 */
function PeerActionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(PEER_STEPS, { active });
  const actionsIn = phase !== 'bubble';
  const replyPicked = phase === 'reply' || phase === 'prefilled';
  return (
    <div className={cn(STAGE, 'items-stretch justify-center gap-2')}>
      <MiniBubble
        side="assistant"
        className="w-3/4 space-y-1.5 border-primary/25 bg-primary/10"
      >
        <span className="flex items-center gap-1.5">
          <Handshake className="h-3 w-3 text-primary" />
          <SkeletonLine w="w-10" className="h-1.5" />
        </span>
        <SkeletonLine w="w-full" />
        <SkeletonLine w="w-2/3" />
      </MiniBubble>
      <span
        className={cn(
          'flex gap-1.5 self-start transition-all duration-300',
          actionsIn ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <MiniChip pressed={replyPicked}>
          <Reply className="h-3 w-3" />
          {labels.reply}
        </MiniChip>
        <MiniChip>
          <ShieldOff className="h-3 w-3" />
        </MiniChip>
      </span>
      <span
        className={cn(
          'flex h-6 items-center gap-1.5 rounded-full border border-border bg-background px-2 transition-all duration-300',
          phase === 'prefilled' ? 'opacity-100' : 'opacity-40'
        )}
      >
        <SkeletonLine
          w={phase === 'prefilled' ? 'w-24' : 'w-2'}
          className="h-1.5 transition-all duration-500"
        />
      </span>
    </div>
  );
}

type ProvenancePhase = 'shut' | 'opening' | 'signals' | 'tombstone';
const PROVENANCE_STEPS: readonly TimelineStep<ProvenancePhase>[] = [
  { at: 0, state: 'shut' },
  { at: 900, state: 'opening' },
  { at: 1600, state: 'signals' },
  { at: 2900, state: 'tombstone' },
];

/**
 * Why LIA thinks that: a folded block opens onto its signals, and the last one
 * becomes a tombstone — the source was deleted, and the trace stays dated.
 */
function ProvenanceWhyScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(PROVENANCE_STEPS, { active });
  const open = phase !== 'shut';
  const shown = phase === 'signals' || phase === 'tombstone';

  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-1.5">
        <div className="rounded-md border border-border bg-background px-2 py-1.5">
          <SkeletonLine w="w-4/5" />
          <SkeletonLine w="w-1/2" className="mt-1" />
        </div>

        <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
          <HelpCircle className="h-3 w-3 shrink-0 text-primary" />
          <SkeletonLine w="w-2/5" />
          <ChevronDown
            className={cn(
              'ml-auto h-3 w-3 text-muted-foreground transition-transform duration-500',
              open && 'rotate-180'
            )}
          />
        </div>

        <div
          className={cn(
            'space-y-1 overflow-hidden transition-all duration-500 ease-out',
            shown ? 'max-h-24 opacity-100' : 'max-h-0 opacity-0'
          )}
        >
          <div className="flex items-center gap-1.5 rounded-md border border-border/60 bg-muted/30 px-2 py-1">
            <span className="rounded bg-primary/15 px-1 py-px text-[8px] font-medium uppercase tracking-wide text-primary">
              ●
            </span>
            <SkeletonLine w="w-3/5" />
          </div>
          <div
            className={cn(
              'flex items-center gap-1.5 rounded-md border border-dashed border-border/60 px-2 py-1 transition-opacity duration-500',
              phase === 'tombstone' ? 'opacity-100' : 'opacity-40'
            )}
          >
            <Trash2 className="h-2.5 w-2.5 shrink-0 text-muted-foreground" />
            <SkeletonLine w="w-2/5" className="opacity-60" />
          </div>
        </div>
      </div>
    </div>
  );
}

type EyesPhase = 'watch' | 'think' | 'search' | 'joy';
const EYES_STEPS: readonly TimelineStep<EyesPhase>[] = [
  { at: 0, state: 'watch' },
  { at: 1100, state: 'think' },
  { at: 2300, state: 'search' },
  { at: 3500, state: 'joy' },
];

/** One glowing Cozmo-style eye of the micro-demo, morphing per phase. */
function MiniEye({ phase, right }: { phase: EyesPhase; right?: boolean }) {
  return (
    <span
      className={cn(
        'block h-4 w-5 rounded-[5px] bg-primary shadow-[0_0_8px] shadow-primary/40',
        'transition-all duration-500 ease-out',
        phase === 'watch' && 'translate-y-0.5',
        phase === 'think' && 'h-2.5 -translate-y-0.5',
        phase === 'search' && (right ? 'translate-x-1' : '-translate-x-1'),
        phase === 'joy' && 'h-2 -translate-y-1 rounded-t-[8px] rounded-b-[2px]'
      )}
    />
  );
}

/**
 * The expressive eyes follow the turn: they watch the input, squint upward
 * while thinking, sweep while searching, then smile at the finished answer.
 */
function ExpressiveEyesScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(EYES_STEPS, { active });
  return (
    <div className={cn(STAGE, 'items-center justify-center gap-2.5')}>
      <div className="flex items-center gap-2">
        <MiniEye phase={phase} />
        <MiniEye phase={phase} right />
      </div>
      <MiniBubble side="assistant" className="w-3/5 space-y-1">
        <SkeletonLine w={phase === 'joy' ? 'w-full' : 'w-1/3'} />
        <SkeletonLine w={phase === 'joy' ? 'w-2/3' : 'w-1/5'} className="opacity-60" />
      </MiniBubble>
    </div>
  );
}

export const RESPOND_SCENES: Readonly<Record<string, SceneComponent>> = {
  provenance_why: ProvenanceWhyScene,
  expressive_eyes: ExpressiveEyesScene,
  followup_chips: FollowupChipsScene,
  scroll_return: ScrollReturnScene,
  bubble_actions: BubbleActionsScene,
  selection_actions: SelectionActionsScene,
  share_export: ShareExportScene,
  backstage: BackstageScene,
  peer_actions: PeerActionsScene,
};
