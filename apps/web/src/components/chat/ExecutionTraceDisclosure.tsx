'use client';

/**
 * ExecutionTraceDisclosure — the backstage record under an assistant bubble
 * (Lot 2 P2-V1).
 *
 * Renders the captured execution trace (steps + reasoning + duration) as a
 * collapsed, dependency-free `<details>`-style disclosure so it never pushes
 * the conversation. Steps are grouped by category; the reasoning block shows
 * beneath them. Renders nothing without a trace or when it has no step (a
 * pure-conversation reply).
 *
 * Rendered INSIDE the bubble action row (QA feedback 2026-07-23): a fragment
 * whose toggle is pushed right by `ml-auto` in the row's flex-wrap, and whose
 * expanded panel wraps to a full-width line beneath the row.
 */

import { useState } from 'react';
import { ChevronRight, Cog } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type {
  ExecutionTrace,
  ExecutionTraceStep,
  TraceStepCategory,
} from '@/types/execution-trace';

export interface ExecutionTraceDisclosureProps {
  trace?: ExecutionTrace;
}

const CATEGORY_ORDER: TraceStepCategory[] = ['system', 'context', 'agent', 'tool'];

function groupByCategory(
  steps: ExecutionTraceStep[]
): { category: TraceStepCategory; steps: ExecutionTraceStep[] }[] {
  const buckets = new Map<TraceStepCategory, ExecutionTraceStep[]>();
  for (const step of steps) {
    const list = buckets.get(step.category) ?? [];
    list.push(step);
    buckets.set(step.category, list);
  }
  return CATEGORY_ORDER.filter(c => buckets.has(c)).map(category => ({
    category,
    steps: buckets.get(category)!,
  }));
}

export function ExecutionTraceDisclosure({ trace }: ExecutionTraceDisclosureProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  if (!trace || trace.steps.length === 0) return null;

  // A shown count is a claim: state the TRUE total, omitted steps included
  // (Lot C, 2026-09 — head+tail retention in capTraceSteps).
  const omitted = trace.omittedSteps ?? 0;
  const stepCount = trace.steps.length + omitted;
  const seconds =
    typeof trace.durationMs === 'number' ? (trace.durationMs / 1000).toFixed(1) : null;
  const groups = groupByCategory(trace.steps);

  return (
    <>
      {/* ml-auto: pushed to the RIGHT edge of the action row
          (user feedback 2026-07-19 + 2026-07-23); the expanded panel
          wraps below at full width. */}
      <button
        type="button"
        aria-expanded={open}
        aria-label={t('chat.trace.aria_toggle')}
        onClick={() => setOpen(o => !o)}
        className="ml-auto flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <Cog className="h-3 w-3" aria-hidden="true" />
        <span>{t('chat.trace.summary', { count: stepCount })}</span>
        {seconds !== null && (
          <>
            <span aria-hidden="true">·</span>
            <span>{t('chat.trace.duration', { seconds })}</span>
          </>
        )}
        <ChevronRight
          className={cn('h-3 w-3 transition-transform', open && 'rotate-90')}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="w-full mt-1 space-y-3 rounded-md border border-border/40 bg-muted/20 px-3 py-2">
          {groups.map(group => (
            <div key={group.category}>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t(`chat.trace.category.${group.category}`)}
              </p>
              <ul className="mt-1 space-y-0.5">
                {group.steps.map((step, i) => (
                  <li
                    key={`${step.label}-${i}`}
                    className="flex items-start gap-1.5 text-xs text-foreground/80"
                  >
                    <span aria-hidden="true">{step.emoji}</span>
                    <span>{step.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {omitted > 0 && (
            // Steps are grouped by category, so a positional "gap" marker
            // would be meaningless — the omission is a property of the whole
            // trace and is stated once, as a global note.
            <p className="text-[10px] italic text-muted-foreground">
              {t('chat.trace.omitted', { count: omitted })}
            </p>
          )}

          {trace.reasoning.trim() && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t('chat.trace.reasoning_title')}
              </p>
              <p className="mt-1 whitespace-pre-line text-xs italic text-muted-foreground">
                {trace.reasoning.trim()}
              </p>
            </div>
          )}
        </div>
      )}
    </>
  );
}
