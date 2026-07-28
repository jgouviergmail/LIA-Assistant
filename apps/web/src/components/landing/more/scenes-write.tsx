/**
 * Scenes of section 01 — "When you write": draft persistence, slash
 * commands, screenshot paste, drag-and-drop. Each scene is a looped,
 * timer-driven micro-demo built from the shared primitives; the last phase
 * is the designed resting frame (shown under prefers-reduced-motion).
 */

'use client';

import {
  ArrowUp,
  CheckCircle2,
  FileText,
  Image as ImageIcon,
  RotateCw,
  Search,
  Settings,
  SlidersHorizontal,
} from 'lucide-react';

import { cn } from '@/lib/utils';

import { KeyCap, MiniComposer, MiniSettingRow, SkeletonLine, STAGE } from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type DraftPhase = 'typed' | 'refreshing' | 'restored';
const DRAFT_STEPS: readonly TimelineStep<DraftPhase>[] = [
  { at: 0, state: 'typed' },
  { at: 1800, state: 'refreshing' },
  { at: 2600, state: 'restored' },
];

function DraftSurvivesScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(DRAFT_STEPS, { active });
  return (
    <div className={STAGE}>
      <div
        className={cn(
          'w-full max-w-[220px] transition-opacity duration-300',
          phase === 'refreshing' && 'opacity-25'
        )}
      >
        <MiniComposer trailing={<ArrowUp className="h-3 w-3 text-primary" />}>
          <span className="block truncate text-[10px] text-foreground/80">{labels.typing}</span>
        </MiniComposer>
      </div>
      <RotateCw
        className={cn(
          'absolute h-4 w-4 text-muted-foreground transition-opacity duration-300',
          phase === 'refreshing' ? 'opacity-100' : 'opacity-0',
          phase === 'refreshing' && active && 'animate-spin'
        )}
      />
      <CheckCircle2
        className={cn(
          'absolute right-6 top-4 h-4 w-4 text-primary transition-all duration-300',
          phase === 'restored' ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
        )}
      />
    </div>
  );
}

type SlashPhase = 'idle' | 'open' | 'row1' | 'row2';
const SLASH_STEPS: readonly TimelineStep<SlashPhase>[] = [
  { at: 0, state: 'idle' },
  { at: 700, state: 'open' },
  { at: 1500, state: 'row1' },
  { at: 2300, state: 'row2' },
];

function SlashCommandsScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(SLASH_STEPS, { active });
  const open = phase !== 'idle';
  return (
    <div className={STAGE}>
      <div
        className={cn(
          'mb-2 w-full max-w-[200px] space-y-1 transition-all duration-300',
          open ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
        )}
      >
        <MiniSettingRow icon={Search} highlighted={phase === 'row1'} />
        <MiniSettingRow icon={SlidersHorizontal} highlighted={phase === 'row2'} />
        <MiniSettingRow icon={Settings} />
      </div>
      <div className="w-full max-w-[220px]">
        <MiniComposer>
          <span className="flex items-center gap-1.5">
            <KeyCap>/</KeyCap>
            <SkeletonLine w="w-10" />
          </span>
        </MiniComposer>
      </div>
    </div>
  );
}

type PastePhase = 'idle' | 'pressed' | 'pasted';
const PASTE_STEPS: readonly TimelineStep<PastePhase>[] = [
  { at: 0, state: 'idle' },
  { at: 900, state: 'pressed' },
  { at: 1700, state: 'pasted' },
];

function PasteScreenshotScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(PASTE_STEPS, { active });
  return (
    <div className={STAGE}>
      <div className="mb-3 flex items-center gap-1">
        <KeyCap className={cn(phase === 'pressed' && 'border-primary/60 text-primary')}>
          Ctrl
        </KeyCap>
        <KeyCap className={cn(phase === 'pressed' && 'border-primary/60 text-primary')}>V</KeyCap>
      </div>
      <div className="w-full max-w-[220px]">
        <MiniComposer>
          <span className="flex items-center gap-2">
            <span
              className={cn(
                'flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-primary/40 bg-primary/10 transition-all duration-300',
                phase === 'pasted' ? 'scale-100 opacity-100' : 'scale-50 opacity-0'
              )}
            >
              <ImageIcon className="h-3 w-3 text-primary" />
            </span>
            <SkeletonLine w="w-16" />
          </span>
        </MiniComposer>
      </div>
    </div>
  );
}

type DropPhase = 'idle' | 'dragging' | 'over' | 'dropped';
const DROP_STEPS: readonly TimelineStep<DropPhase>[] = [
  { at: 0, state: 'idle' },
  { at: 600, state: 'dragging' },
  { at: 1500, state: 'over' },
  { at: 2300, state: 'dropped' },
];

function DropZoneScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(DROP_STEPS, { active });
  const flying = phase === 'dragging' || phase === 'over';
  return (
    <div className={STAGE}>
      <div
        className={cn(
          'flex h-16 w-full max-w-[220px] items-center justify-center rounded-lg border-2 border-dashed transition-colors duration-300',
          phase === 'over' ? 'border-primary/70 bg-primary/5' : 'border-border'
        )}
      >
        <FileText
          className={cn(
            'absolute h-5 w-5 text-muted-foreground transition-all duration-700 ease-out',
            phase === 'idle' && 'left-6 top-4 opacity-0',
            flying && 'left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-100',
            phase === 'dropped' && 'left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-0'
          )}
        />
        <span
          className={cn(
            'flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 transition-all duration-300',
            phase === 'dropped' ? 'scale-100 opacity-100' : 'scale-75 opacity-0'
          )}
        >
          <FileText className="h-3 w-3 text-primary" />
          <SkeletonLine w="w-10" className="bg-primary/25" />
        </span>
      </div>
    </div>
  );
}

export const WRITE_SCENES: Readonly<Record<string, SceneComponent>> = {
  draft_survives: DraftSurvivesScene,
  slash_commands: SlashCommandsScene,
  paste_screenshot: PasteScreenshotScene,
  drop_zone: DropZoneScene,
};
