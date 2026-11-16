/**
 * The small picture at the top of each argument tile (owner, 2026-11-15):
 * built from the landing's own pieces (Lucide glyphs, the Tools' yellow stars,
 * the cosmos gradient), never drawn by hand, never animated. Decorative: the
 * tile's title and text say what it shows. Server-safe markup.
 */

import type { ReactNode } from 'react';

import { AssistStars } from '@/components/selection-assist/AssistStars';
import {
  Bot,
  Calendar,
  Check,
  Gauge,
  House,
  Lightbulb,
  Mail,
  MousePointerClick,
  Phone,
  Repeat,
  ShieldCheck,
  User,
} from '@/lib/icons';
import { cn } from '@/lib/utils';

import type { ArgumentId } from '../comparison/comparison-data';

const CHIP =
  'flex items-center justify-center border border-primary/30 bg-background/90 text-primary shadow-sm';
const LINE = 'h-1.5 rounded-full bg-foreground/15';

/** A plan checked step by step, beside the loop that searches by itself. */
function AgentVignette() {
  return (
    <div className="flex items-center gap-4">
      <div className="space-y-1.5 rounded-lg border border-border/70 bg-background/90 p-2.5 shadow-sm">
        {['w-14', 'w-10', 'w-12'].map(width => (
          <div key={width} className="flex items-center gap-1.5">
            <span className="flex size-4 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Check className="size-3" />
            </span>
            <span className={cn(LINE, width)} />
          </div>
        ))}
      </div>
      <span className={cn(CHIP, 'size-12 rounded-full')}>
        <Bot className="size-6" />
      </span>
      <span className={cn(CHIP, 'size-9 rounded-full')}>
        <Repeat className="size-4" />
      </span>
    </div>
  );
}

/** Everyday tools worked by hand, and the yellow stars that call LIA in. */
function ManualVignette() {
  return (
    <div className="relative">
      <div className="w-52 space-y-2 rounded-lg border border-border/70 bg-background/90 p-2.5 shadow-sm">
        <div className="flex items-center gap-2">
          <Mail className="size-3.5 shrink-0 text-primary" />
          <span className={cn(LINE, 'w-20 bg-foreground/25')} />
          <AssistStars className="ml-auto size-4" />
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="size-3.5 shrink-0 text-primary" />
          <span className={cn(LINE, 'w-24')} />
        </div>
        <div className="flex items-center gap-2">
          <Lightbulb className="size-3.5 shrink-0 text-primary" />
          <span className={cn(LINE, 'w-16')} />
        </div>
      </div>
      <MousePointerClick className="absolute -right-3 top-6 size-5 text-muted-foreground" />
    </div>
  );
}

const AVATAR_TINTS = [
  'bg-[color-mix(in_srgb,var(--cosmos-blue)_18%,transparent)] text-[var(--cosmos-blue)]',
  'bg-[color-mix(in_srgb,var(--cosmos-violet)_18%,transparent)] text-[var(--cosmos-violet)]',
  'bg-[color-mix(in_srgb,var(--cosmos-cyan)_22%,transparent)] text-[var(--cosmos-cyan)]',
] as const;

/** Several people, one home. */
function FamilyVignette() {
  return (
    <div className="flex items-center gap-4">
      <div className="flex -space-x-3">
        {AVATAR_TINTS.map(tint => (
          <span
            key={tint}
            className={cn(
              'flex size-11 items-center justify-center rounded-full border-2 border-background',
              tint
            )}
          >
            <User className="size-5" />
          </span>
        ))}
      </div>
      <span className={cn(CHIP, 'size-10 rounded-xl')}>
        <House className="size-5" />
      </span>
    </div>
  );
}

/** A fixed waveform: each bar's place is its identity. */
const WAVE = [
  { bar: 'b1', height: 'h-3' },
  { bar: 'b2', height: 'h-6' },
  { bar: 'b3', height: 'h-9' },
  { bar: 'b4', height: 'h-5' },
  { bar: 'b5', height: 'h-11' },
  { bar: 'b6', height: 'h-7' },
  { bar: 'b7', height: 'h-4' },
  { bar: 'b8', height: 'h-8' },
  { bar: 'b9', height: 'h-5' },
  { bar: 'b10', height: 'h-3' },
] as const;

/** A voice heard live, and the phone. */
function VoiceVignette() {
  return (
    <div className="flex items-center gap-5">
      <div className="flex h-12 items-center gap-1">
        {WAVE.map(({ bar, height }) => (
          <span
            key={bar}
            className={cn('w-1.5 rounded-full [background:var(--cosmos-grad)]', height)}
          />
        ))}
      </div>
      <span className={cn(CHIP, 'size-10 rounded-full')}>
        <Phone className="size-4" />
      </span>
    </div>
  );
}

/** Spending caps and a watched instance. */
function GovernanceVignette() {
  return (
    <div className="flex min-w-0 items-center gap-5">
      <div className="w-40 min-w-0 space-y-2">
        <div className="h-2 rounded-full bg-foreground/10">
          <div className="h-2 w-2/5 rounded-full [background:var(--cosmos-grad)]" />
        </div>
        <div className="h-2 rounded-full bg-foreground/10">
          <div className="h-2 w-3/4 rounded-full bg-primary/60" />
        </div>
        <div className="h-2 rounded-full bg-foreground/10">
          <div className="h-2 w-1/4 rounded-full bg-primary/35" />
        </div>
      </div>
      <span className={cn(CHIP, 'size-10 shrink-0 rounded-full')}>
        <ShieldCheck className="size-5" />
      </span>
      <span className={cn(CHIP, 'size-9 shrink-0 rounded-full')}>
        <Gauge className="size-4" />
      </span>
    </div>
  );
}

const VIGNETTES: Readonly<Record<ArgumentId, () => ReactNode>> = {
  agentic: AgentVignette,
  manual: ManualVignette,
  family: FamilyVignette,
  voice: VoiceVignette,
  governance: GovernanceVignette,
};

/** The vignette of one argument, in its framed band. */
export function ArgumentVignette({ id }: { id: ArgumentId }) {
  const Picture = VIGNETTES[id];
  return (
    <div
      aria-hidden="true"
      data-vignette={id}
      className="mb-5 flex h-24 items-center justify-center overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-primary/10 via-background/40 to-transparent"
    >
      <Picture />
    </div>
  );
}
