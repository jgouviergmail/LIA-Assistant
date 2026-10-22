'use client';

import { CheckCircle2, ListTodo, Sparkles, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { HeadingRule } from '@/components/ui/heading-rule';
import { Skeleton } from '@/components/ui/skeleton';
import type { PersonalResults } from '@/hooks/usePersonalResults';

import { DashboardTile, TILE_ICON_BADGE } from './DashboardTile';

/**
 * What the assistant ACHIEVED, ahead of what it consumed.
 *
 * The dashboard opened on messages, tokens, Google requests and cost: figures
 * an administrator needs and a reader cannot act on. They are still there,
 * grouped behind "Consumption"; this block takes the lead instead.
 *
 * **Nothing here is estimated.** Each figure is an exact aggregate over its own
 * set. Two candidates were dropped rather than approximated: "time saved",
 * which nothing in this system measures, and "documents actually used" — an
 * injected chunk is not a used one, and no table records the difference.
 *
 * **An unmeasured instance says so.** Rendering four zeros where outcome
 * recording is disabled would tell the reader they achieved nothing, which is
 * a different claim from "nothing is being counted" — and a false one.
 */
export interface ResultsSummaryProps {
  results: PersonalResults | undefined;
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  error: Error | null;
  /** BCP-47 locale for number and date formatting. */
  locale: string;
}

interface Achievement {
  key: string;
  value: number;
  icon: LucideIcon;
}

export function ResultsSummary({ results, firstLoad, error, locale }: ResultsSummaryProps) {
  const { t } = useTranslation();

  if (firstLoad) {
    return (
      <div
        role="status"
        aria-label={t('common.loading')}
        className="grid grid-cols-2 gap-3 lg:grid-cols-4"
      >
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-28 rounded-2xl" />
        ))}
      </div>
    );
  }

  // Absent rather than wrong: a block showing zeros because a request failed
  // would misreport the reader's month. `error` is read explicitly rather than
  // left implied by `!results` — the intent is a decision, not a side effect.
  if (error || !results) return null;

  if (!results.measured) {
    return (
      <section aria-labelledby={RESULTS_HEADING_ID}>
        <SectionHeading />
        <p className="mt-3 text-sm italic text-muted-foreground">
          {t('dashboard.results.not_measured')}
        </p>
      </section>
    );
  }

  const achievements: Achievement[] = [
    { key: 'useful_results', value: results.useful_results, icon: CheckCircle2 },
    { key: 'actions', value: results.actions, icon: Zap },
    { key: 'automations', value: results.automations, icon: Sparkles },
    { key: 'commitments_closed', value: results.commitments_closed, icon: ListTodo },
  ];

  const cycleLabel = formatCycleStart(results.cycle_start, locale);

  return (
    <section aria-labelledby={RESULTS_HEADING_ID}>
      <SectionHeading />
      {cycleLabel && (
        <p className="mt-3 text-xs text-muted-foreground">
          {t('dashboard.results.since', { date: cycleLabel })}
        </p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* The page's tile material, with no hover lift: these tiles are a
            readout, nothing here is clickable, and a lift would promise an
            action that does not exist. */}
        {achievements.map(({ key, value, icon: Icon }) => (
          <DashboardTile
            key={key}
            contentClassName="grid min-w-0 grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 p-4"
          >
            <span className={TILE_ICON_BADGE} aria-hidden="true">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="min-w-0 text-2xl font-bold tabular-nums text-primary [overflow-wrap:anywhere]">
              {formatCount(value, locale)}
            </span>
            <span className="col-span-2 break-words text-xs leading-relaxed text-muted-foreground">
              {t(`dashboard.results.${key}`)}
            </span>
          </DashboardTile>
        ))}
      </div>
    </section>
  );
}

const RESULTS_HEADING_ID = 'dashboard-results-heading';

/**
 * A rubrique of the home page, never folded (owner request 2026-10-21): the
 * heading runs on into the hairline every page-level rubrique draws.
 */
function SectionHeading() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-11 items-center gap-2 py-2">
      <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      <h2
        id={RESULTS_HEADING_ID}
        className="min-w-0 text-base font-semibold tracking-tight text-foreground sm:text-lg"
      >
        {t('dashboard.results.title')}
      </h2>
      <HeadingRule />
    </div>
  );
}

/** Locale-grouped count; the raw number rather than a crash on a bad locale. */
function formatCount(value: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(value);
  } catch {
    return String(value);
  }
}

/** Cycle start, or null when it cannot be read (the line is then omitted). */
function formatCycleStart(iso: string, locale: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long' }).format(date);
  } catch {
    return null;
  }
}
