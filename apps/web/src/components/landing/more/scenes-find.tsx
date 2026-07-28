/**
 * Scenes of section 04 — "When you search": everyday-words settings search,
 * settings deep links, full history search, the phone logo navigation.
 * Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import { Hash, Link2, Moon, Palette, Search, SunMedium } from 'lucide-react';

import { cn } from '@/lib/utils';

import { Cursor, MiniSettingRow, PhoneFrame, SkeletonLine, STAGE } from './primitives';
import type { SceneComponent, SceneProps } from './scene-types';
import { useLoopedTimeline, type TimelineStep } from './useLoopedTimeline';

type SearchPhase = 'typing' | 'typed' | 'results' | 'highlight';
const SEARCH_STEPS: readonly TimelineStep<SearchPhase>[] = [
  { at: 0, state: 'typing' },
  { at: 700, state: 'typed' },
  { at: 1400, state: 'results' },
  { at: 2200, state: 'highlight' },
];

function SettingsSearchScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(SEARCH_STEPS, { active });
  const showResults = phase === 'results' || phase === 'highlight';
  return (
    <div className={cn(STAGE, 'justify-center gap-2')}>
      <div className="flex w-full max-w-[200px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <Search className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="text-[10px] text-foreground/80">
          {phase === 'typing' ? '' : labels.query}
          <span
            className={cn(
              'ml-px inline-block h-2.5 w-px bg-foreground/70 align-middle',
              phase !== 'typing' && phase !== 'typed' && 'opacity-0'
            )}
          />
        </span>
      </div>
      <div
        className={cn(
          'w-full max-w-[200px] space-y-1 transition-all duration-300',
          showResults ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <MiniSettingRow icon={Moon} label={labels.row1} highlighted={phase === 'highlight'} />
        <MiniSettingRow icon={Palette} label={labels.row2} />
      </div>
    </div>
  );
}

type DeepPhase = 'link' | 'navigate' | 'highlight';
const DEEP_STEPS: readonly TimelineStep<DeepPhase>[] = [
  { at: 0, state: 'link' },
  { at: 1100, state: 'navigate' },
  { at: 1900, state: 'highlight' },
];

function DeepLinksScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(DEEP_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-3')}>
      <span
        className={cn(
          'flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 transition-colors duration-300',
          phase !== 'link' && 'border-primary/50'
        )}
      >
        <Link2 className="h-3 w-3 text-primary" />
        <Hash className="h-3 w-3 text-muted-foreground" />
        <SkeletonLine w="w-14" />
      </span>
      <div
        className={cn(
          'w-full max-w-[200px] space-y-1 transition-transform duration-500 ease-out',
          phase === 'link' ? 'translate-y-2' : 'translate-y-0'
        )}
      >
        <MiniSettingRow icon={SunMedium} />
        <MiniSettingRow icon={Moon} highlighted={phase === 'highlight'} />
      </div>
    </div>
  );
}

type HistoryPhase = 'typed' | 'rows' | 'match';
const HISTORY_STEPS: readonly TimelineStep<HistoryPhase>[] = [
  { at: 0, state: 'typed' },
  { at: 800, state: 'rows' },
  { at: 1700, state: 'match' },
];

function HistorySearchScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(HISTORY_STEPS, { active });
  const rowsIn = phase !== 'typed';
  return (
    <div className={cn(STAGE, 'justify-center gap-2')}>
      <div className="flex w-full max-w-[200px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <Search className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="text-[10px] text-foreground/80">{labels.query}</span>
      </div>
      <div
        className={cn(
          'w-full max-w-[200px] space-y-1 transition-all duration-300',
          rowsIn ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        )}
      >
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
          <SkeletonLine w="w-3/5" />
        </div>
        <div
          className={cn(
            'flex items-center gap-2 rounded-md border bg-background px-2 py-1.5 transition-colors duration-300',
            phase === 'match' ? 'border-primary/60' : 'border-border'
          )}
        >
          <span
            className={cn(
              'rounded-sm px-1 text-[10px] transition-colors duration-300',
              phase === 'match' ? 'bg-primary/15 text-primary' : 'text-foreground/80'
            )}
          >
            {labels.query}
          </span>
          <SkeletonLine w="w-2/5" />
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
          <SkeletonLine w="w-1/2" />
        </div>
      </div>
    </div>
  );
}

type LogoPhase = 'idle' | 'tap' | 'open';
const LOGO_STEPS: readonly TimelineStep<LogoPhase>[] = [
  { at: 0, state: 'idle' },
  { at: 900, state: 'tap' },
  { at: 1500, state: 'open' },
];

function MobileLogoNavScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(LOGO_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <PhoneFrame>
        <div className="flex flex-col items-center gap-1">
          <span
            className={cn(
              'flex h-4 w-4 items-center justify-center rounded-full bg-primary/15 transition-transform duration-200',
              phase === 'tap' && 'scale-90'
            )}
          >
            <span className="h-2 w-2 rounded-full bg-primary" />
          </span>
          <div
            className={cn(
              'w-full space-y-1 transition-all duration-300',
              phase === 'open' ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0'
            )}
          >
            <SkeletonLine w="w-full" className="h-1.5" />
            <SkeletonLine w="w-4/5" className="h-1.5" />
            <SkeletonLine w="w-full" className="h-1.5" />
            <SkeletonLine w="w-3/5" className="h-1.5" />
          </div>
        </div>
      </PhoneFrame>
      <Cursor
        className={cn(
          phase === 'idle'
            ? 'left-[62%] top-[65%] opacity-100'
            : 'left-[53%] top-[24%] opacity-100',
          phase === 'open' && 'opacity-0'
        )}
      />
    </div>
  );
}

export const FIND_SCENES: Readonly<Record<string, SceneComponent>> = {
  settings_search: SettingsSearchScene,
  deep_links: DeepLinksScene,
  history_search: HistorySearchScene,
  mobile_logo_nav: MobileLogoNavScene,
};
