/**
 * Scenes of section 04 — "When you search": the master-detail settings shell,
 * the group tones that turn a flat list into a map, the everyday-words settings
 * search, settings deep links that survive a reload, full history search, the
 * phone logo navigation.
 * Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import {
  Bell,
  ChevronDown,
  Fingerprint,
  Hash,
  Link2,
  Moon,
  Palette,
  PanelLeft,
  Plug,
  RotateCw,
  Search,
  Star,
} from 'lucide-react';

import { SETTINGS_GROUP_TONES } from '@/lib/settings-group-tones';

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

type ShellPhase = 'rail' | 'picking' | 'open';
const SHELL_STEPS: readonly TimelineStep<ShellPhase>[] = [
  { at: 0, state: 'rail' },
  { at: 1000, state: 'picking' },
  { at: 1600, state: 'open' },
];

/**
 * The master-detail settings shell (ADR-227): a permanent rail of sections
 * beside a pane that opens exactly one of them, whole.
 */
function SettingsShellScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(SHELL_STEPS, { active });
  const open = phase === 'open';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="flex w-full max-w-[220px] gap-2">
        {/* The rail — always there, never scrolled away. */}
        <div className="w-[38%] shrink-0 space-y-1">
          {[0, 1, 2, 3].map(row => (
            <div
              key={row}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-1.5 py-1 transition-colors duration-300',
                row === 1 && phase !== 'rail' ? 'bg-primary/10' : 'bg-transparent'
              )}
            >
              <span
                className={cn(
                  'h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-300',
                  row === 1 && phase !== 'rail' ? 'bg-primary' : 'bg-muted-foreground/30'
                )}
              />
              <SkeletonLine w="w-full" className="h-1.5" />
            </div>
          ))}
        </div>
        {/* The pane — one section, open, with room to breathe. */}
        <div
          className={cn(
            'min-w-0 flex-1 rounded-lg border bg-background p-2 transition-all duration-500 ease-out',
            open
              ? 'translate-x-0 border-border opacity-100'
              : 'translate-x-1 border-border/40 opacity-40'
          )}
        >
          <span className="flex items-center gap-1.5">
            <PanelLeft className="h-3 w-3 shrink-0 text-primary" />
            <span className="truncate text-[9px] font-medium text-foreground/80">
              {labels.section}
            </span>
          </span>
          <span
            className={cn(
              'mt-1.5 block space-y-1 overflow-hidden transition-all duration-500 ease-out',
              open ? 'max-h-16 opacity-100' : 'max-h-0 opacity-0'
            )}
          >
            <SkeletonLine w="w-5/6" className="h-1.5" />
            <SkeletonLine w="w-2/3" className="h-1.5" />
            <SkeletonLine w="w-3/4" className="h-1.5" />
          </span>
        </div>
      </div>
      <Cursor
        className={cn(
          'left-[22%] top-[42%] transition-opacity',
          phase === 'picking' ? 'opacity-100' : 'opacity-0'
        )}
      />
    </div>
  );
}

type DeepPhase = 'link' | 'navigate' | 'reload';
const DEEP_STEPS: readonly TimelineStep<DeepPhase>[] = [
  { at: 0, state: 'link' },
  { at: 1100, state: 'navigate' },
  { at: 2100, state: 'reload' },
];

/**
 * A section's address SURVIVES: since the shell keeps `?section=` in the URL,
 * reloading or sharing lands on the very same open panel. The old scene showed
 * a link highlighting an accordion row — a page that no longer exists.
 */
function DeepLinksScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(DEEP_STEPS, { active });
  const landed = phase !== 'link';
  return (
    <div className={cn(STAGE, 'justify-center gap-2.5')}>
      <span
        className={cn(
          'flex items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 transition-colors duration-300',
          landed ? 'border-primary/50' : 'border-border'
        )}
      >
        <Link2 className="h-3 w-3 text-primary" />
        <Hash className="h-3 w-3 text-muted-foreground" />
        <SkeletonLine w="w-12" />
        <RotateCw
          className={cn(
            'h-3 w-3 transition-all duration-500',
            phase === 'reload' ? 'rotate-180 text-primary' : 'text-muted-foreground/40'
          )}
        />
      </span>
      {/* The same panel, open, before and after the reload — the point being
          that nothing had to be found again. */}
      <div
        className={cn(
          'w-full max-w-[190px] rounded-lg border border-border bg-background p-2 transition-all duration-500 ease-out',
          landed ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
        )}
      >
        <span className="flex items-center gap-1.5">
          <Moon className="h-3 w-3 shrink-0 text-primary" />
          <SkeletonLine w="w-1/2" className="h-1.5" />
        </span>
        <span className="mt-1.5 block space-y-1">
          <SkeletonLine w="w-full" className="h-1.5" />
          <SkeletonLine w="w-2/3" className="h-1.5" />
        </span>
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

type StarPhase = 'plain' | 'starred' | 'promoted';
const STAR_STEPS: readonly TimelineStep<StarPhase>[] = [
  { at: 0, state: 'plain' },
  { at: 1100, state: 'starred' },
  { at: 2100, state: 'promoted' },
];

/** A relation card gets starred in place, then rises into the favorites band. */
function RelationStarScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(STAR_STEPS, { active });
  const starred = phase !== 'plain';
  return (
    <div className={cn(STAGE, 'justify-center gap-2')}>
      <div className="flex items-center gap-1.5">
        <Star
          className={cn(
            'h-3.5 w-3.5 transition-colors duration-300',
            phase === 'promoted' ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/40'
          )}
        />
        <SkeletonLine w="w-14" className="h-1.5" />
      </div>
      <div
        className={cn(
          'relative flex w-3/4 items-center gap-2 self-center rounded-lg border bg-background p-2 transition-all duration-500 ease-out',
          phase === 'promoted'
            ? '-translate-y-2 border-amber-500/40 shadow-md'
            : 'translate-y-0 border-border'
        )}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/15 text-[9px] font-bold text-primary">
          GD
        </span>
        <span className="flex-1 space-y-1">
          <SkeletonLine w="w-2/3" />
          <SkeletonLine w="w-1/3" className="h-1" />
        </span>
        <Star
          className={cn(
            'h-3.5 w-3.5 shrink-0 transition-all duration-300',
            starred
              ? 'scale-110 fill-amber-400 text-amber-400'
              : 'scale-100 text-muted-foreground/40'
          )}
        />
        <Cursor
          className={cn(
            phase === 'plain' ? 'right-[8%] top-[80%] opacity-100' : 'right-[6%] top-[35%]',
            phase === 'promoted' && 'opacity-0'
          )}
        />
      </div>
    </div>
  );
}

type FoldPhase = 'folded' | 'opening' | 'open';
const FOLD_STEPS: readonly TimelineStep<FoldPhase>[] = [
  { at: 0, state: 'folded' },
  { at: 1200, state: 'opening' },
  { at: 1700, state: 'open' },
];

/** A relationship sheet is an index: every section folded, one opens on demand. */
function RelationSectionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(FOLD_STEPS, { active });
  const open = phase === 'open';
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5')}>
      {[0, 1, 2].map(row => (
        <div
          key={row}
          className="w-3/4 self-center rounded-lg border border-border bg-background px-2 py-1.5"
        >
          <span className="flex items-center gap-1.5">
            <ChevronDown
              className={cn(
                'h-3 w-3 shrink-0 text-muted-foreground transition-transform duration-300',
                !(open && row === 1) && '-rotate-90'
              )}
            />
            {row === 1 ? (
              <span className="text-[9px] font-medium text-foreground/80">{labels.section}</span>
            ) : (
              <SkeletonLine w="w-1/2" className="h-1.5" />
            )}
          </span>
          {row === 1 && (
            <span
              className={cn(
                'mt-1 block space-y-1 overflow-hidden transition-all duration-300 ease-out',
                open ? 'max-h-8 opacity-100' : 'max-h-0 opacity-0'
              )}
            >
              <SkeletonLine w="w-5/6" className="h-1" />
              <SkeletonLine w="w-2/3" className="h-1" />
            </span>
          )}
        </div>
      ))}
      <Cursor
        className={cn(
          'right-[18%] top-[46%] transition-opacity',
          phase === 'folded' ? 'opacity-100' : 'opacity-0'
        )}
      />
    </div>
  );
}

type TonesPhase = 'flat' | 'toned';
const TONES_STEPS: readonly TimelineStep<TonesPhase>[] = [
  { at: 0, state: 'flat' },
  { at: 1300, state: 'toned' },
];

/**
 * The settings list before and after v1.38.1: one repeated glyph in one ink —
 * `Plug`, which really did serve four different settings — then a drawing per
 * section in its family's tone.
 *
 * The three glyphs are the ones the registry actually assigns (Fingerprint,
 * Bell, Palette); the labels name the FAMILY, which is what the card is about.
 *
 * The tones are READ from `SETTINGS_GROUP_TONES`, never restated here — this
 * stage would otherwise become a second, drifting authority on a palette the
 * contrast guard measures elsewhere.
 */
function SettingsTonesScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(TONES_STEPS, { active });
  const toned = phase === 'toned';
  // Keyed by the label slot, not the translated text: two locales are free to
  // render the same word for two rows without React seeing one element.
  const rows = [
    { key: 'row1', icon: Fingerprint, label: labels.row1, tone: SETTINGS_GROUP_TONES.security },
    {
      key: 'row2',
      icon: Bell,
      label: labels.row2,
      tone: SETTINGS_GROUP_TONES.notifications_communication,
    },
    {
      key: 'row3',
      icon: Palette,
      label: labels.row3,
      tone: SETTINGS_GROUP_TONES.personalization,
    },
  ];
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5')}>
      {rows.map(row => (
        <MiniSettingRow
          key={row.key}
          className="max-w-[200px]"
          icon={toned ? row.icon : Plug}
          label={row.label}
          iconClassName={toned ? row.tone.glyph : 'text-muted-foreground'}
        />
      ))}
    </div>
  );
}

export const FIND_SCENES: Readonly<Record<string, SceneComponent>> = {
  settings_shell: SettingsShellScene,
  settings_tones: SettingsTonesScene,
  settings_search: SettingsSearchScene,
  deep_links: DeepLinksScene,
  history_search: HistorySearchScene,
  mobile_logo_nav: MobileLogoNavScene,
  relation_star: RelationStarScene,
  relation_sections: RelationSectionsScene,
};
