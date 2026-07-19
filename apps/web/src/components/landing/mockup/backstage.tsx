'use client';

import { useTranslation } from 'react-i18next';
import { Check, Phone, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatEuro, formatNumber } from '@/lib/format';
import type { Language } from '@/i18n/settings';

/**
 * The signature element of the hero mockup: while LIA "thinks", a glass pane
 * slides over the chat and reveals the real orchestration (an honest styling
 * of the actual debug panel / SSE execution steps). Each act draws a different
 * figure on the same grammar: fan-out, self-linking spark, live call, forge.
 * Everything is decorative (spans + aria-hidden SVG), benefit vocabulary only.
 */

export interface BackstageProps {
  label: string;
  /** Live cost line: tokens spent + EUR, counted while agents run. */
  cost: { tokens: number; costEur: number };
  costLabel: string;
  children: React.ReactNode;
}

export function Backstage({ label, cost, costLabel, children }: BackstageProps) {
  const { t, i18n } = useTranslation();
  const lng = i18n.language as Language;
  return (
    <div className="absolute inset-0 flex flex-col items-center gap-1.5 px-4 py-2.5 bg-gradient-to-b from-primary/10 via-transparent to-primary/10 backdrop-blur-[1.5px] animate-glass-in">
      <span className="flex items-center gap-2 text-[8px] font-bold uppercase tracking-[0.22em] text-primary">
        <span className="w-10 h-px bg-primary/40" />
        {label}
        <span className="w-10 h-px bg-primary/40" />
      </span>
      {children}
      <span className="mt-auto flex items-center gap-1 text-[9px] text-muted-foreground tabular-nums">
        <Zap className="w-2.5 h-2.5 text-amber-500" />
        <span className="font-semibold text-foreground">
          {formatNumber(cost.tokens, lng)} {t('landing.chat_mockup.tokens_unit')} ·{' '}
          {formatEuro(cost.costEur, 3, lng)}
        </span>
        — {costLabel}
      </span>
    </div>
  );
}

/** The user request, condensed into a pill at the top of the figure. */
export function BsQuery({ text }: { text: string }) {
  return (
    <span className="max-w-[92%] truncate rounded-full border border-border bg-card px-3 py-0.5 text-[10px] text-foreground animate-chip-pop">
      {text}
    </span>
  );
}

/** Fan-out ('split') or converge ('join') connector between figure rows. */
export function BsFan({ direction }: { direction: 'split' | 'join' }) {
  const paths =
    direction === 'split'
      ? ['M150,2 C150,16 52,14 52,26', 'M150,2 L150,26', 'M150,2 C150,16 248,14 248,26']
      : ['M52,2 C52,14 150,12 150,26', 'M150,2 L150,26', 'M248,2 C248,14 150,12 150,26'];
  return (
    <svg
      className="w-full max-w-[300px] h-5 shrink-0"
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
        />
      ))}
    </svg>
  );
}

export type BsChipState = 'run' | 'done';

/** One parallel task: a domain chip that works (progress) then checks green. */
export function BsChip({ label, sub, state }: { label: string; sub: string; state: BsChipState }) {
  return (
    <span
      className={cn(
        'relative block flex-1 max-w-[124px] rounded-lg border bg-card px-1.5 py-1 text-center animate-chip-pop',
        state === 'done' ? 'border-green-500/40' : 'border-primary ring-2 ring-primary/15'
      )}
    >
      {state === 'done' && (
        <span className="absolute -top-1.5 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-green-600 animate-chip-pop">
          <Check className="w-2.5 h-2.5 text-white" />
        </span>
      )}
      <span className="block text-[10px] font-semibold text-foreground leading-tight">{label}</span>
      <span className="block text-[8.5px] text-muted-foreground leading-tight truncate">{sub}</span>
      {state === 'run' && (
        <span className="mt-0.5 block h-[3px] rounded-full bg-muted overflow-hidden">
          <span className="block h-full w-3/5 rounded-full bg-primary animate-step-breathe" />
        </span>
      )}
    </span>
  );
}

/** The HITL gate: amber while holding the flow, green once approval is given. */
export function BsGate({
  text,
  tone,
  pulse = false,
}: {
  text: string;
  tone: 'amber' | 'green';
  pulse?: boolean;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg border-[1.5px] px-3 py-1 text-[10px] font-semibold animate-chip-pop',
        tone === 'amber'
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300'
          : 'border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300',
        pulse && 'animate-gate-pulse'
      )}
    >
      🛡️ {text}
      {tone === 'green' && <Check className="w-3 h-3" />}
    </span>
  );
}

/** Vertical connector between two figure rows. */
export function BsStem() {
  return <span className="h-3 w-px shrink-0 bg-primary/50" aria-hidden="true" />;
}

/** Two chips linking themselves: the proactivity spark (act 2). */
export function BsSparkLink({
  left,
  right,
  spark,
  wiresDrawn,
  sparkShown,
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  spark: string;
  wiresDrawn: boolean;
  sparkShown: boolean;
}) {
  const wire = cn(
    'h-px w-7 shrink-0 bg-primary/50',
    wiresDrawn ? 'animate-wire-draw' : 'scale-x-0'
  );
  return (
    <span className="flex items-center justify-center w-full">
      {left}
      <span className={cn(wire, 'origin-left')} />
      <span
        className={cn(
          'z-10 -mx-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-[1.5px] border-violet-500/40 bg-violet-500/10 text-xs',
          sparkShown ? 'animate-chip-pop' : 'opacity-0'
        )}
      >
        {spark}
      </span>
      <span className={cn(wire, 'origin-right')} />
      {right}
    </span>
  );
}

/** Live outbound phone call: the flow reaching the real world (act 3). */
export function BsCall({ name, sub }: { name: string; sub: string }) {
  return (
    <span className="flex items-center gap-2 rounded-lg border border-primary bg-card px-3 py-1.5 ring-2 ring-primary/15 animate-chip-pop">
      <Phone className="w-3.5 h-3.5 text-primary" />
      <span className="text-left">
        <span className="block text-[10px] font-semibold leading-tight text-foreground">
          {name}
        </span>
        <span className="block text-[8.5px] leading-tight text-muted-foreground tabular-nums">
          {sub}
        </span>
      </span>
      <span className="flex h-3.5 items-end gap-0.5 text-primary" aria-hidden="true">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className="w-0.5 h-full origin-bottom rounded-full bg-current animate-typing-eq"
            style={{ animationDelay: `${i * -0.18}s` }}
          />
        ))}
      </span>
    </span>
  );
}

/** Capability rail: existing domains + the freshly forged skill node (act 4). */
export function BsRail({ plugged }: { plugged: boolean }) {
  const domains = ['✉️', '📅', '👥', '🌦️', '💡'];
  return (
    <span className="flex items-center gap-1.5" aria-hidden="true">
      {domains.map(d => (
        <span
          key={d}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-xs"
        >
          {d}
        </span>
      ))}
      <span
        className={cn(
          'flex h-7 w-7 items-center justify-center rounded-lg border text-xs font-bold',
          plugged
            ? 'border-cyan-500/50 bg-cyan-500/15 text-cyan-600 dark:text-cyan-300 animate-chip-pop'
            : 'border-dashed border-cyan-500/40 text-transparent'
        )}
      >
        ✦
      </span>
    </span>
  );
}

/** The skill forge: code generated, sandboxed, installed (act 4). */
export function BsForge({ label, sub }: { label: string; sub: string }) {
  return (
    <span className="flex flex-col items-center gap-0.5 rounded-lg border border-cyan-500/40 bg-card px-3.5 py-1.5 animate-chip-pop">
      <span className="text-[10px] font-semibold text-cyan-600 dark:text-cyan-300">✨ {label}</span>
      <span className="block h-[3px] w-24 rounded-full bg-muted overflow-hidden">
        <span className="block h-full w-4/5 rounded-full bg-cyan-500 animate-step-breathe" />
      </span>
      <span className="text-[8.5px] text-muted-foreground">{sub}</span>
    </span>
  );
}

/** Explanatory line under a figure (violet = initiative, cyan = creation…). */
export function BsNote({ tone, text }: { tone: 'violet' | 'cyan' | 'muted'; text: string }) {
  const tones = {
    violet: 'border-violet-500/30 bg-violet-500/10 text-violet-800 dark:text-violet-200',
    cyan: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-200',
    muted: 'border-transparent bg-transparent text-muted-foreground italic',
  };
  return (
    <span
      className={cn(
        'block max-w-[94%] rounded-lg border px-2.5 py-1 text-center text-[9.5px] leading-snug animate-chip-pop',
        tones[tone]
      )}
    >
      {text}
    </span>
  );
}
