import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Translate } from './FeatureCatalog';

/**
 * Backstage vignettes — the hero animation decomposed. Each chapter that is
 * not illustrated by a chat scene gets a standalone figure drawn in the
 * mockup's backstage grammar (fan-out, self-linking spark, forge + rail),
 * with content deliberately different from the hero's four acts.
 *
 * Decorative: rendered inside an aria-hidden ScrollStage; the fill-both
 * keyframes stay paused until the stage becomes visible (see globals.css).
 * Stagger is driven per element via `--stage-delay`.
 */

/**
 * Per-element stagger. The keyframes stay `animation-play-state: paused`
 * until the ScrollStage becomes visible; pausing freezes the delay countdown
 * too, so a plain animation-delay choreographs from the reveal moment.
 */
function stage(delayMs: number): React.CSSProperties {
  return { animationDelay: `${delayMs}ms` };
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative mx-auto flex w-full max-w-md flex-col items-center gap-3 rounded-2xl border border-border/70 bg-gradient-to-b from-primary/[0.07] via-transparent to-primary/[0.07] px-6 py-8">
      {children}
    </div>
  );
}

function PanelLabel({ text }: { text: string }) {
  return (
    <span className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.22em] text-primary">
      <span className="h-px w-10 bg-primary/40" />
      {text}
      <span className="h-px w-10 bg-primary/40" />
    </span>
  );
}

function QueryPill({ text }: { text: string }) {
  return (
    <span
      className="min-w-0 max-w-[92%] truncate rounded-full border border-border bg-card px-3.5 py-1 text-xs text-foreground animate-chip-pop"
      style={stage(0)}
    >
      {text}
    </span>
  );
}

function Fan({ direction, delayMs }: { direction: 'split' | 'join'; delayMs: number }) {
  const paths =
    direction === 'split'
      ? ['M150,2 C150,16 52,14 52,26', 'M150,2 L150,26', 'M150,2 C150,16 248,14 248,26']
      : ['M52,2 C52,14 150,12 150,26', 'M150,2 L150,26', 'M248,2 C248,14 150,12 150,26'];
  return (
    <svg
      className="h-5 w-full max-w-[300px] shrink-0"
      viewBox="0 0 300 28"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {paths.map(d => (
        <path
          key={d}
          d={d}
          pathLength={1}
          fill="none"
          strokeWidth="1.3"
          strokeDasharray="0.06 0.055"
          className="stroke-primary/60 animate-fan-draw"
          style={stage(delayMs)}
        />
      ))}
    </svg>
  );
}

function TaskChip({
  title,
  sub,
  state,
  delayMs,
}: {
  title: string;
  sub: string;
  state: 'run' | 'done';
  delayMs: number;
}) {
  return (
    <span
      className={cn(
        'relative block min-w-0 max-w-[136px] flex-1 rounded-lg border bg-card px-2 py-1.5 text-center animate-chip-pop',
        state === 'done' ? 'border-green-500/40' : 'border-primary ring-2 ring-primary/15'
      )}
      style={stage(delayMs)}
    >
      {state === 'done' && (
        <span
          className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-green-600 animate-chip-pop"
          style={stage(delayMs + 350)}
        >
          <Check className="h-2.5 w-2.5 text-white" />
        </span>
      )}
      <span className="block text-[11px] font-semibold leading-tight text-foreground">{title}</span>
      <span className="block truncate text-[9px] leading-tight text-muted-foreground">{sub}</span>
      {state === 'run' && (
        <span className="mt-1 block h-[3px] overflow-hidden rounded-full bg-muted">
          <span className="block h-full w-3/5 rounded-full bg-primary animate-step-breathe" />
        </span>
      )}
    </span>
  );
}

/** Chapter 01 — one sentence fans out; a whole series lands (FOR_EACH). */
export function VignetteOrchestration({ t }: { t: Translate }) {
  const k = (s: string) => t(`landing.chapters.c1.${s}`);
  return (
    <Panel>
      <PanelLabel text={t('landing.chapters.backstage_label')} />
      <QueryPill text={k('v_query')} />
      <Fan direction="split" delayMs={250} />
      <span className="flex w-full justify-center gap-2">
        <TaskChip title={k('v_t1')} sub={k('v_t1_sub')} state="done" delayMs={450} />
        <TaskChip title={k('v_t2')} sub={k('v_t2_sub')} state="done" delayMs={650} />
        <TaskChip title={k('v_t3')} sub={k('v_t3_sub')} state="run" delayMs={850} />
      </span>
      <Fan direction="join" delayMs={1100} />
      <span
        className="rounded-lg border border-green-500/40 border-l-[3px] border-l-green-600 bg-card px-3 py-1.5 text-xs text-foreground animate-chip-pop"
        style={stage(1350)}
      >
        ✅ <strong className="font-bold">{k('v_series')}</strong> — {k('v_series_sub')}
      </span>
    </Panel>
  );
}

/** Chapter 03 — two domains link themselves: the proactivity spark. */
export function VignetteSpark({ t }: { t: Translate }) {
  const k = (s: string) => t(`landing.chapters.c3.${s}`);
  return (
    <Panel>
      <PanelLabel text={t('landing.chapters.backstage_label')} />
      <span className="text-[10px] italic text-muted-foreground animate-chip-pop" style={stage(0)}>
        {k('v_intro')}
      </span>
      <span className="flex w-full items-center justify-center">
        <TaskChip title={k('v_left')} sub={k('v_left_sub')} state="done" delayMs={200} />
        <span
          className="h-px w-7 shrink-0 origin-left bg-primary/50 animate-wire-draw"
          style={stage(600)}
        />
        <span
          className="z-10 -mx-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-[1.5px] border-violet-500/40 bg-violet-500/10 text-sm animate-chip-pop"
          style={stage(900)}
        >
          ✨
        </span>
        <span
          className="h-px w-7 shrink-0 origin-right bg-primary/50 animate-wire-draw"
          style={stage(600)}
        />
        <TaskChip title={k('v_right')} sub={k('v_right_sub')} state="done" delayMs={400} />
      </span>
      <span
        className="max-w-[94%] rounded-xl border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-center text-xs leading-snug text-violet-800 dark:text-violet-200 animate-chip-pop"
        style={stage(1200)}
      >
        ✨ {k('v_note')}
      </span>
    </Panel>
  );
}

/** Chapter 05 — a skill is forged, then plugs into the capability rail. */
export function VignetteForge({ t }: { t: Translate }) {
  const k = (s: string) => t(`landing.chapters.c5.${s}`);
  const domains = ['✉️', '📅', '👥', '🌦️', '💡', '📚'];
  return (
    <Panel>
      <PanelLabel text={t('landing.chapters.backstage_label')} />
      <span
        className="flex flex-col items-center gap-1 rounded-lg border border-cyan-500/40 bg-card px-4 py-2 animate-chip-pop"
        style={stage(0)}
      >
        <span className="text-[11px] font-semibold text-cyan-600 dark:text-cyan-300">
          ✨ {k('v_forge')}
        </span>
        <span className="block h-[3px] w-24 overflow-hidden rounded-full bg-muted">
          <span className="block h-full w-4/5 rounded-full bg-cyan-500 animate-step-breathe" />
        </span>
        <span className="text-[9px] text-muted-foreground">{k('v_forge_sub')}</span>
      </span>
      <span className="h-3.5 w-px bg-primary/50 animate-wire-draw" style={stage(400)} />
      <span className="flex items-center gap-1.5">
        {domains.map((d, i) => (
          <span
            key={d}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-card text-sm animate-chip-pop"
            style={stage(500 + i * 90)}
          >
            {d}
          </span>
        ))}
        <span
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/50 bg-cyan-500/15 text-sm font-bold text-cyan-600 dark:text-cyan-300 animate-chip-pop"
          style={stage(1200)}
        >
          ✦
        </span>
      </span>
      <span
        className="max-w-[94%] text-center text-[10px] text-muted-foreground animate-chip-pop"
        style={stage(1450)}
      >
        📚 {k('v_docs')}
      </span>
    </Panel>
  );
}
