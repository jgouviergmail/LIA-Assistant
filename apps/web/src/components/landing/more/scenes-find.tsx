/**
 * Scenes of section 04 — "When you search": the master-detail settings shell,
 * the group tones that turn a flat list into a map, the everyday-words settings
 * search, settings deep links that survive a reload, full history search, the
 * minutes-template library whose categories open closed, the phone logo
 * navigation, the written debrief that opens a relationship card, one button
 * per kind of action on a person's page, a
 * relationship's rows dated like an e-mail, the number a place shares between
 * its list row and its pin, and the sandbox-network permissions a person
 * revokes in place. Timer-driven micro-demos; last phase = resting frame.
 */

'use client';

import {
  ArrowDown,
  Bell,
  Blocks,
  Check,
  ChevronDown,
  Fingerprint,
  FolderTree,
  Footprints,
  Globe,
  Hash,
  KeyRound,
  Link2,
  Mail,
  MessageSquare,
  Moon,
  Navigation,
  NotebookPen,
  Palette,
  PanelLeft,
  PhoneCall,
  Pin,
  Plug,
  RefreshCw,
  RotateCw,
  Search,
  ShieldCheck,
  Star,
  Undo2,
  UserRound,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { SETTINGS_GROUP_TONES } from '@/lib/settings-group-tones';
import { directionTone } from '@/lib/status-tone';

import { cn } from '@/lib/utils';

import { Cursor, MiniChip, MiniSettingRow, PhoneFrame, SkeletonLine, STAGE } from './primitives';
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
        <span className="text-px-10 text-foreground/80">
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
            <span className="truncate text-px-9 font-medium text-foreground/80">
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
        <span className="text-px-10 text-foreground/80">{labels.query}</span>
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
              'rounded-sm px-1 text-px-10 transition-colors duration-300',
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
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/15 text-px-9 font-bold text-primary">
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
              <span className="text-px-9 font-medium text-foreground/80">{labels.section}</span>
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

type LibraryPhase = 'closed' | 'opening' | 'ticked' | 'added';
const LIBRARY_STEPS: readonly TimelineStep<LibraryPhase>[] = [
  { at: 0, state: 'closed' },
  { at: 900, state: 'opening' },
  { at: 1700, state: 'ticked' },
  { at: 2400, state: 'added' },
];

/** Categories shut by default: the reader opens the one that concerns them. */
function TemplateLibraryScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(LIBRARY_STEPS, { active });
  const opened = phase !== 'closed';
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5 px-6')}>
      <div className="flex w-full max-w-[210px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="text-px-10 text-primary">{labels.mine}</span>
      </div>
      <div className="w-full max-w-[210px]">
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
          <ChevronDown
            className={cn(
              'h-3 w-3 shrink-0 text-muted-foreground transition-transform duration-300 motion-reduce:transition-none',
              opened && 'rotate-180'
            )}
          />
          <span className="text-px-10 text-primary">{labels.builtin}</span>
          {phase === 'added' && (
            <span className="ml-auto rounded-full bg-primary/10 px-1.5 text-px-9 text-primary">
              {labels.pick}
            </span>
          )}
        </div>
        <div
          className={cn(
            'grid overflow-hidden transition-[grid-template-rows] duration-300 motion-reduce:transition-none',
            opened ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          )}
        >
          <div className="min-h-0 space-y-1 pl-4 pt-1">
            {[0, 1].map(row => (
              <div key={row} className="flex items-center gap-2">
                <span
                  className={cn(
                    'h-2.5 w-2.5 shrink-0 rounded-[3px] border border-border transition-colors duration-200 motion-reduce:transition-none',
                    row === 0 &&
                      (phase === 'ticked' || phase === 'added') &&
                      'border-primary bg-primary'
                  )}
                />
                <SkeletonLine w={row === 0 ? 'w-2/3' : 'w-1/2'} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

type MailLabelPhase = 'plain' | 'labelled' | 'landing' | 'indexed';
const MAIL_LABEL_STEPS: readonly TimelineStep<MailLabelPhase>[] = [
  { at: 0, state: 'plain' },
  { at: 900, state: 'labelled' },
  { at: 1700, state: 'landing' },
  { at: 2500, state: 'indexed' },
];

/** A label put on a thread is the whole opt-in: the thread joins the space. */
function MailLabelSourceScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(MAIL_LABEL_STEPS, { active });
  const labelled = phase !== 'plain';
  const arrived = phase === 'landing' || phase === 'indexed';
  return (
    <div className={cn(STAGE, 'justify-center gap-2 px-6')}>
      <div className="flex w-full max-w-[210px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <SkeletonLine w="w-1/2" />
        <span
          className={cn(
            'ml-auto rounded-full px-1.5 text-px-9 transition-opacity duration-300 motion-reduce:transition-none',
            labelled ? 'bg-primary/10 text-primary opacity-100' : 'opacity-0'
          )}
        >
          {labels.label}
        </span>
      </div>

      <ArrowDown
        className={cn(
          'h-3 w-3 text-muted-foreground transition-opacity duration-300 motion-reduce:transition-none',
          arrived ? 'opacity-100' : 'opacity-0'
        )}
        aria-hidden="true"
      />

      <div className="w-full max-w-[210px] rounded-md border border-border bg-background px-2 py-1.5">
        <div className="flex items-center gap-2">
          <span className="text-px-10 text-primary">{labels.space}</span>
          {phase === 'indexed' && (
            <span className="ml-auto rounded-full bg-primary/10 px-1.5 text-px-9 text-primary">
              {labels.indexed}
            </span>
          )}
        </div>
        <div
          className={cn(
            'grid overflow-hidden transition-[grid-template-rows] duration-300 motion-reduce:transition-none',
            arrived ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          )}
        >
          <div className="min-h-0 pt-1">
            <SkeletonLine w="w-2/3" />
          </div>
        </div>
      </div>
    </div>
  );
}

type DebriefPhase = 'sections' | 'writing' | 'written';
const DEBRIEF_STEPS: readonly TimelineStep<DebriefPhase>[] = [
  { at: 0, state: 'sections' },
  { at: 900, state: 'writing' },
  { at: 2100, state: 'written' },
];

/**
 * The relationship card no longer opens on ten sections (ADR-269).
 *
 * The scene animates the ORDER a reader meets: the stack of sections is what
 * was there, the synthesis lands ABOVE it, and the resting frame is the one
 * with the debrief in place — because that is the state the page settles in,
 * not the moment of writing.
 */
function RelationDebriefScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(DEBRIEF_STEPS, { active });
  const writing = phase === 'writing';
  const written = phase === 'written';

  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-1.5">
        {/* The synthesis, above everything the card already stacked. */}
        <div
          className={cn(
            'grid overflow-hidden transition-[grid-template-rows,opacity] duration-500 motion-reduce:transition-none',
            writing || written ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
          )}
        >
          <div className="min-h-0">
            <div className="space-y-1.5 rounded-lg border border-primary/40 bg-primary/5 p-2">
              <div className="flex items-center gap-1.5">
                <NotebookPen
                  className={cn(
                    'h-3 w-3 shrink-0 text-primary',
                    writing && 'animate-pulse motion-reduce:animate-none'
                  )}
                  aria-hidden="true"
                />
                <SkeletonLine w="w-2/3" />
              </div>
              <div
                className={cn(
                  'space-y-1 transition-opacity duration-300 motion-reduce:transition-none',
                  written ? 'opacity-100' : 'opacity-0'
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-px-9 text-primary">{labels.open}</span>
                  <SkeletonLine w="w-1/2" />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-px-9 text-primary">{labels.next}</span>
                  <SkeletonLine w="w-2/5" />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* What the card always held, pushed down rather than replaced. */}
        {[0, 1, 2].map(row => (
          <div key={row} className="rounded-md border border-border bg-background px-2 py-1.5">
            <SkeletonLine w={row === 1 ? 'w-1/2' : 'w-3/5'} />
          </div>
        ))}
      </div>
    </div>
  );
}

type GroupedPhase = 'bar' | 'hover' | 'menu' | 'picked';
const GROUPED_STEPS: readonly TimelineStep<GroupedPhase>[] = [
  { at: 0, state: 'bar' },
  { at: 700, state: 'hover' },
  { at: 1300, state: 'menu' },
  { at: 2200, state: 'picked' },
];

/** The action kinds of the bar: the first one holds several addresses. */
const GROUPED_KINDS = [Mail, Navigation, PhoneCall] as const;

/**
 * One button per kind of action on a person's page; the kind with several
 * addresses opens a menu that names each one in the reader's language.
 */
function GroupedActionsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(GROUPED_STEPS, { active });
  const open = phase === 'menu' || phase === 'picked';
  return (
    <div className={cn(STAGE, 'justify-start gap-1.5 pt-6')}>
      <div className="flex w-3/4 items-center gap-1.5">
        <UserRound className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
        <SkeletonLine w="w-1/2" />
      </div>
      <div className="relative grid w-3/4 grid-cols-3 gap-1.5">
        {GROUPED_KINDS.map((Icon, index) => (
          <span
            key={index}
            className={cn(
              'flex h-6 items-center justify-center gap-0.5 rounded-md bg-primary text-primary-foreground transition-shadow duration-300 motion-reduce:transition-none',
              index === 0 && phase !== 'bar' && 'ring-2 ring-primary/30'
            )}
          >
            <Icon className="h-3 w-3" aria-hidden="true" />
            {index === 0 && <ChevronDown className="h-2.5 w-2.5" aria-hidden="true" />}
          </span>
        ))}
        <div
          className={cn(
            'absolute left-0 top-full mt-1 w-32 rounded-md border border-border bg-background py-0.5 shadow-sm transition-all duration-300 ease-out motion-reduce:transition-none',
            open ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0'
          )}
        >
          {[labels.home, labels.work].map((label, row) => (
            <span
              key={row}
              className={cn(
                'flex items-center gap-1.5 px-1.5 py-1 text-px-9',
                phase === 'picked' && row === 0 && 'bg-primary/10'
              )}
            >
              <Mail className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
              <span className="font-medium text-foreground/80">{label}</span>
              <SkeletonLine w="w-10" className="h-1" />
            </span>
          ))}
        </div>
      </div>
      <Cursor
        className={cn(
          phase === 'picked' ? 'left-[24%] top-[60%]' : 'left-[26%] top-[38%]',
          phase === 'bar' ? 'opacity-0' : 'opacity-100'
        )}
      />
    </div>
  );
}

type DockPhase = 'open' | 'folded' | 'moved' | 'reopened';
const DOCK_STEPS: readonly TimelineStep<DockPhase>[] = [
  { at: 0, state: 'open' },
  { at: 1100, state: 'folded' },
  { at: 1900, state: 'moved' },
  { at: 2900, state: 'reopened' },
];

/**
 * The pinned dock: it sits, folds into a dot, is dragged low, and unfolds
 * UPWARD from there — the one behaviour a still screenshot cannot show, and
 * the reason the capsule never leaves the screen when it is parked near the
 * bottom edge.
 */
function PinnedDockScene({ active }: SceneProps) {
  const phase = useLoopedTimeline(DOCK_STEPS, { active });
  const folded = phase === 'folded' || phase === 'moved';
  const low = phase === 'moved' || phase === 'reopened';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      {/* The page under it, indifferent. */}
      <div className="absolute inset-3 space-y-1.5" aria-hidden="true">
        <SkeletonLine w="w-2/3" className="h-1.5" />
        <SkeletonLine w="w-1/2" className="h-1.5" />
        <SkeletonLine w="w-3/5" className="h-1.5" />
      </div>
      <div
        className={cn(
          'absolute right-4 flex flex-col items-center justify-end gap-1 rounded-full border border-primary/40 bg-background/95 p-1 shadow-sm',
          'transition-all duration-700 ease-out',
          low ? 'bottom-3' : 'bottom-9'
        )}
      >
        {/* Folded, only the grip shows; unfolded, the pinned sections stack
            ABOVE it, so the foot stays where the dot was. */}
        <span
          className={cn(
            'flex flex-col items-center gap-1 overflow-hidden transition-all duration-500 ease-out',
            folded ? 'max-h-0 opacity-0' : 'max-h-16 opacity-100'
          )}
        >
          <Moon className="h-3 w-3 text-primary" />
          <Bell className="h-3 w-3 text-primary" />
          <Search className="h-3 w-3 text-primary" />
        </span>
        <Pin
          className={cn(
            'h-3 w-3 shrink-0 transition-colors duration-300',
            folded ? 'text-primary' : 'text-muted-foreground'
          )}
        />
      </div>
    </div>
  );
}

type SyncCountPhase = 'idle' | 'counting' | 'asked';
const SYNC_COUNT_STEPS: readonly TimelineStep<SyncCountPhase>[] = [
  { at: 0, state: 'idle' },
  { at: 800, state: 'counting' },
  { at: 2200, state: 'asked' },
];

/**
 * Past the threshold the Sync button counts first, then states the exact
 * number of files about to be indexed and waits for the person.
 */
function SyncCountScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(SYNC_COUNT_STEPS, { active });
  return (
    <div className={cn(STAGE, 'justify-center gap-2 px-6')}>
      <div className="flex w-full max-w-[220px] items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
        <FolderTree className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
        <SkeletonLine w="w-1/3" />
        <span
          className={cn(
            'ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-px-9 transition-colors motion-reduce:transition-none',
            phase === 'idle'
              ? 'border-border text-foreground'
              : 'border-primary/40 bg-primary/10 text-primary'
          )}
        >
          <RefreshCw
            className={cn('h-2.5 w-2.5', phase === 'counting' && 'motion-safe:animate-spin')}
            aria-hidden="true"
          />
          {phase === 'counting' ? labels.counting : labels.sync}
        </span>
      </div>
      <div
        className={cn(
          'w-full max-w-[220px] rounded-md border border-border bg-background p-2 text-px-10 shadow-sm transition-all duration-300 motion-reduce:transition-none',
          phase === 'asked'
            ? 'translate-y-0 opacity-100'
            : 'pointer-events-none translate-y-1 opacity-0'
        )}
      >
        <p className="font-medium text-foreground">
          <span className="text-primary">37</span> {labels.files}
        </p>
        <div className="mt-1 flex gap-1">
          {['w-6', 'w-8', 'w-5', 'w-7'].map(w => (
            <SkeletonLine key={w} w={w} />
          ))}
        </div>
        <div className="mt-2 flex justify-end gap-1">
          <span className="rounded border border-border px-1.5 py-0.5 text-muted-foreground">
            …
          </span>
          <span className="rounded bg-primary px-1.5 py-0.5 text-primary-foreground">
            {labels.confirm}
          </span>
        </div>
      </div>
    </div>
  );
}

type NetworkGrantsPhase = 'list' | 'hover' | 'revoked' | 'rest';
const NETWORK_GRANTS_STEPS: readonly TimelineStep<NetworkGrantsPhase>[] = [
  { at: 0, state: 'list' },
  { at: 1400, state: 'hover' },
  { at: 2400, state: 'revoked' },
  { at: 3800, state: 'rest' },
];

/**
 * Settings › Skill permissions (ADR-298): the hosts reachable without asking,
 * then the person's own permissions — one of them revoked on the spot. The
 * resting frame shows the list whole (row, scope, revoke button): a card at
 * rest must show what the attention IS, not the instant after it was used.
 */
function NetworkGrantsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(NETWORK_GRANTS_STEPS, { active });
  const revoked = phase === 'revoked';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-1.5 text-px-10">
        <div className="px-1 text-px-9 uppercase tracking-wide text-muted-foreground">
          {labels.reachable}
        </div>
        <MiniSettingRow icon={Globe} label={labels.connector} iconClassName="text-primary" />
        <div
          className={cn(
            'grid overflow-hidden transition-[grid-template-rows,opacity] duration-500 motion-reduce:transition-none',
            revoked ? 'grid-rows-[0fr] opacity-0' : 'grid-rows-[1fr] opacity-100'
          )}
        >
          <div className="min-h-0">
            <div
              className={cn(
                'flex w-full items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5',
                phase === 'hover' && 'ring-2 ring-primary/60'
              )}
            >
              <KeyRound className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate font-mono text-foreground/80">
                {labels.grant}
              </span>
              <span className="truncate text-px-9 text-muted-foreground">{labels.scope}</span>
              <span className="rounded-full border border-border px-1.5 py-0.5 text-px-9 text-destructive">
                {labels.revoke}
              </span>
            </div>
          </div>
        </div>
        <div
          className={cn(
            'px-1 text-px-9 text-muted-foreground transition-opacity duration-300',
            revoked ? 'opacity-100' : 'opacity-0'
          )}
        >
          {labels.revoked}
        </div>
      </div>
      <Cursor
        className={cn(
          phase === 'hover' ? 'left-[78%] top-[58%] opacity-100' : 'left-[60%] top-[90%] opacity-0'
        )}
      />
    </div>
  );
}

type SkillLibraryPhase = 'search' | 'results' | 'read' | 'installed';
const SKILL_LIBRARY_STEPS: readonly TimelineStep<SkillLibraryPhase>[] = [
  { at: 0, state: 'search' },
  { at: 900, state: 'results' },
  { at: 1900, state: 'read' },
  { at: 3000, state: 'installed' },
];
const SKILL_LIBRARY_ORDER: readonly SkillLibraryPhase[] = [
  'search',
  'results',
  'read',
  'installed',
];

/**
 * « Find skills » (ADR-327): a search in a public library, the result opened
 * and read — audits and files checked — then installed. The resting frame
 * keeps every line: what installs is what was read.
 */
function SkillLibraryScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(SKILL_LIBRARY_STEPS, { active });
  const reached = (step: SkillLibraryPhase) =>
    SKILL_LIBRARY_ORDER.indexOf(phase) >= SKILL_LIBRARY_ORDER.indexOf(step);
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="w-full max-w-[210px] space-y-1.5 text-px-10">
        <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
          <Search className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate text-foreground/80">{labels.query}</span>
        </div>
        <div
          className={cn(
            'flex items-center gap-2 rounded-md border px-2 py-1.5 transition-all duration-300 motion-reduce:transition-none',
            reached('results') ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0',
            reached('read') ? 'border-primary/60 bg-background' : 'border-border bg-background'
          )}
        >
          <Blocks className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate font-medium text-foreground/80">
            {labels.result}
          </span>
          {reached('installed') ? (
            <span className="flex items-center gap-1 rounded-full bg-primary/15 px-1.5 py-0.5 text-px-9 font-medium text-primary">
              <Check className="h-2.5 w-2.5" aria-hidden="true" />
              {labels.installed}
            </span>
          ) : null}
        </div>
        <div
          className={cn(
            'flex items-center gap-1.5 px-1 text-px-9 text-muted-foreground transition-opacity duration-300 motion-reduce:transition-none',
            reached('read') ? 'opacity-100' : 'opacity-0'
          )}
        >
          <ShieldCheck className="h-3 w-3 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate">{labels.audit}</span>
        </div>
      </div>
    </div>
  );
}

type FrozenPhase = 'start' | 'scrolled';
const FROZEN_STEPS: readonly TimelineStep<FrozenPhase>[] = [
  { at: 0, state: 'start' },
  { at: 1400, state: 'scrolled' },
];

/** One row of switches: on, off, on, on, off — read by its colour alone here. */
const FROZEN_SWITCHES = [true, false, true, true, false, true, false, true] as const;

/**
 * The administrators' user table: every per-account switch is a column, the
 * table scrolls sideways, and the e-mail and the name stay put. Resting
 * frame: scrolled, the identity still in view.
 */
function FrozenColumnsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(FROZEN_STEPS, { active });
  return (
    <div className={cn(STAGE, 'gap-1')}>
      {[0, 1, 2].map(row => (
        <div
          key={row}
          className="flex w-full max-w-[240px] items-center overflow-hidden rounded border border-border bg-background text-px-9"
        >
          <span className="w-[42%] shrink-0 truncate border-r border-border bg-background px-1.5 py-1 font-medium text-foreground/80">
            {row === 0 ? labels.email : <SkeletonLine w="w-4/5" className="h-1.5" />}
          </span>
          <div className="min-w-0 flex-1 overflow-hidden">
            <div
              className={cn(
                'flex gap-1.5 px-1.5 transition-transform duration-1000 ease-in-out',
                phase === 'scrolled' ? '-translate-x-10' : 'translate-x-0'
              )}
            >
              {FROZEN_SWITCHES.map((on, index) => (
                <span
                  key={index}
                  className={cn(
                    'h-2 w-3.5 shrink-0 rounded-full',
                    row === 0
                      ? 'bg-muted-foreground/25'
                      : on !== (row === 2)
                        ? 'bg-primary/70'
                        : 'bg-muted-foreground/25'
                  )}
                />
              ))}
            </div>
          </div>
        </div>
      ))}
      <span className="text-px-9 text-muted-foreground">{labels.switches}</span>
    </div>
  );
}

type BackPhase = 'list' | 'open' | 'back' | 'restored';
const BACK_STEPS: readonly TimelineStep<BackPhase>[] = [
  { at: 0, state: 'list' },
  { at: 1000, state: 'open' },
  { at: 2200, state: 'back' },
  { at: 2800, state: 'restored' },
];

/**
 * Back where you were: opening an item hides the list instead of rebuilding
 * it, so the search, the filter and the highlighted row are still there when
 * you come back.
 */
function BackWhereYouWereScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(BACK_STEPS, { active });
  const detail = phase === 'open' || phase === 'back';
  return (
    <div className={cn(STAGE, 'justify-center')}>
      <div className="relative h-28 w-full max-w-[210px] overflow-hidden rounded-lg border border-border bg-background shadow-sm">
        <div
          className={cn(
            'space-y-1.5 p-2 transition-opacity duration-300',
            detail ? 'opacity-0' : 'opacity-100'
          )}
        >
          <div className="flex items-center gap-1.5 rounded-md border border-border px-1.5 py-1">
            <Search className="h-2.5 w-2.5 shrink-0 text-muted-foreground" />
            <span className="truncate text-px-9 text-foreground/80">{labels.query}</span>
          </div>
          <MiniChip pressed className="text-px-9">
            {labels.filter}
          </MiniChip>
          <SkeletonLine w="w-4/5" />
          <div
            className={cn(
              'rounded-md px-1 py-0.5 transition-colors duration-500',
              phase === 'restored' ? 'bg-primary/10' : 'bg-transparent'
            )}
          >
            <SkeletonLine w="w-3/5" />
          </div>
        </div>
        <div
          className={cn(
            'absolute inset-0 space-y-1.5 bg-background p-2 transition-transform duration-500 ease-out',
            detail ? 'translate-x-0' : 'translate-x-full'
          )}
        >
          <MiniChip pressed={phase === 'back'} className="text-px-9">
            <Undo2 className="h-2.5 w-2.5" />
            {labels.back}
          </MiniChip>
          <SkeletonLine w="w-2/3" />
          <SkeletonLine w="w-full" />
          <SkeletonLine w="w-4/5" />
        </div>
      </div>
    </div>
  );
}

type PlacePhase = 'list' | 'pick' | 'details';
const PLACE_STEPS: readonly TimelineStep<PlacePhase>[] = [
  { at: 0, state: 'list' },
  { at: 900, state: 'pick' },
  { at: 1700, state: 'details' },
];

/** Three places: the number each carries, and where its pin sits on the map. */
const PLACE_PINS = [
  { n: 1, left: '24%', top: '30%' },
  { n: 2, left: '64%', top: '52%' },
  { n: 3, left: '36%', top: '74%' },
] as const;

/**
 * Position's numbered places (ADR-356): one number per place, the same in the
 * list and on its pin. Selecting row 2 lights pin 2 and opens the details the
 * answer already gathered, with one route — no new search (ADR-355).
 */
function PlaceNumbersScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(PLACE_STEPS, { active });
  const picked = phase !== 'list';
  return (
    <div className={cn(STAGE, 'flex-row items-center gap-2.5')}>
      <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-lg border border-border bg-background">
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 bg-muted-foreground/10" />
        <div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 bg-muted-foreground/10" />
        {PLACE_PINS.map(pin => (
          <span
            key={pin.n}
            className={cn(
              'absolute flex h-4 w-4 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border text-px-9 font-semibold transition-all duration-300',
              picked && pin.n === 2
                ? 'scale-125 border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background text-muted-foreground'
            )}
            style={{ left: pin.left, top: pin.top }}
          >
            {pin.n}
          </span>
        ))}
      </div>
      <div className="flex w-28 flex-col gap-1">
        {PLACE_PINS.map(pin => (
          <span
            key={pin.n}
            className={cn(
              'flex items-center gap-1.5 rounded-md border border-border bg-background px-1.5 py-1 transition-shadow duration-300',
              picked && pin.n === 2 && 'ring-2 ring-primary/60'
            )}
          >
            <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-muted text-px-9 font-semibold text-foreground/80">
              {pin.n}
            </span>
            <SkeletonLine w="w-14" className="h-1.5" />
          </span>
        ))}
        <span
          className={cn(
            'flex flex-col gap-1 overflow-hidden rounded-md border border-border bg-background px-1.5 transition-all duration-500 ease-out',
            phase === 'details' ? 'max-h-14 py-1 opacity-100' : 'max-h-0 py-0 opacity-0'
          )}
        >
          <span className="text-px-9 font-medium text-foreground/80">{labels.details}</span>
          <MiniChip className="self-start px-1.5 py-0.5 text-px-9">
            <Footprints className="h-2.5 w-2.5" />
            {labels.route}
          </MiniChip>
        </span>
      </div>
      <Cursor
        className={cn(
          'right-[14%] top-[46%] transition-opacity',
          phase === 'pick' ? 'opacity-100' : 'opacity-0'
        )}
      />
    </div>
  );
}

type DatedPhase = 'plain' | 'dated';
const DATED_STEPS: readonly TimelineStep<DatedPhase>[] = [
  { at: 0, state: 'plain' },
  { at: 1200, state: 'dated' },
];

/** A call LIA placed and an SMS the phone relayed: the row kind and its direction. */
const DATED_ROWS = [
  { direction: 'sent', icon: PhoneCall },
  { direction: 'received', icon: MessageSquare },
] as const;

/**
 * A relationship's rows titled like an e-mail (`RelationWhen`): how long ago
 * and when, in bold, then what the row is about, with no icon in front; a call
 * or an SMS opens on its direction, in the tone `directionTone` gives the real
 * badge — read, never restated here.
 */
function DatedRowsScene({ active, labels }: SceneProps) {
  const phase = useLoopedTimeline(DATED_STEPS, { active });
  const dated = phase === 'dated';
  return (
    <div className={cn(STAGE, 'justify-center gap-1.5')}>
      {DATED_ROWS.map(({ direction, icon: Icon }) => (
        <div
          key={direction}
          className="w-4/5 rounded-lg border border-border bg-background px-2 py-1.5"
        >
          <span
            className={cn(
              'block overflow-hidden text-px-9 text-foreground/80 transition-all duration-500',
              dated ? 'max-h-5 opacity-100' : 'max-h-0 opacity-0'
            )}
          >
            <strong>{labels.ago}</strong> · <strong>{labels.when}</strong>
          </span>
          <span className="mt-1 flex items-center gap-1.5">
            {dated ? (
              <Badge variant={directionTone(direction)} size="sm">
                {labels[direction]}
              </Badge>
            ) : (
              <Icon className="h-3 w-3 shrink-0 text-muted-foreground" />
            )}
            <SkeletonLine w="w-1/2" className="h-1.5" />
          </span>
        </div>
      ))}
    </div>
  );
}

export const FIND_SCENES: Readonly<Record<string, SceneComponent>> = {
  place_numbers: PlaceNumbersScene,
  dated_rows: DatedRowsScene,
  settings_shell: SettingsShellScene,
  settings_tones: SettingsTonesScene,
  settings_search: SettingsSearchScene,
  frozen_columns: FrozenColumnsScene,
  deep_links: DeepLinksScene,
  history_search: HistorySearchScene,
  template_library: TemplateLibraryScene,
  mail_label_source: MailLabelSourceScene,
  sync_count: SyncCountScene,
  mobile_logo_nav: MobileLogoNavScene,
  relation_star: RelationStarScene,
  relation_sections: RelationSectionsScene,
  relation_debrief: RelationDebriefScene,
  grouped_actions: GroupedActionsScene,
  pinned_dock: PinnedDockScene,
  network_grants: NetworkGrantsScene,
  skill_library: SkillLibraryScene,
  back_where_you_were: BackWhereYouWereScene,
};
