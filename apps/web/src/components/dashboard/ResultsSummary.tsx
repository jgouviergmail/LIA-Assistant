'use client';

import { CheckCircle2, ListTodo, Sparkles, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent } from '@/components/ui/card';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type { PersonalResults } from '@/hooks/usePersonalResults';

/**
 * What the assistant ACHIEVED, ahead of what it consumed.
 *
 * The dashboard opened on messages, tokens, Google requests and cost: figures
 * an administrator needs and a reader cannot act on. They are still there,
 * folded behind "Consumption"; this block takes the lead instead.
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
      <div className="flex justify-center py-6">
        <LoadingSpinner className="h-5 w-5" />
      </div>
    );
  }

  // Absent rather than wrong: a block showing zeros because a request failed
  // would misreport the reader's month. `error` is read explicitly rather than
  // left implied by `!results` — the intent is a decision, not a side effect.
  if (error || !results) return null;

  if (!results.measured) {
    return (
      <section>
        <SectionHeading />
        <p className="text-sm italic text-muted-foreground">
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
    <section>
      <SectionHeading />
      {cycleLabel && (
        <p className="mb-3 text-xs text-muted-foreground">
          {t('dashboard.results.since', { date: cycleLabel })}
        </p>
      )}
      {/* One column on the narrowest screens, two from `sm`, four from `lg`:
          a four-up row at 320 px would leave ~70 px per tile. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card `default`, not `elevated`: these tiles are a readout, nothing
            here is clickable, and `elevated` lifts its shadow on hover — an
            affordance promising an action that does not exist. */}
        {achievements.map(({ key, value, icon: Icon }) => (
          <Card key={key} className="border-border/50">
            <CardContent className="flex items-center gap-3 p-4">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block text-2xl font-bold tabular-nums text-foreground">
                  {formatCount(value, locale)}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {t(`dashboard.results.${key}`)}
                </span>
              </span>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function SectionHeading() {
  const { t } = useTranslation();
  return (
    <h2 className="mb-2 flex items-center gap-2 text-base font-semibold tracking-tight text-foreground sm:text-lg">
      <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      {t('dashboard.results.title')}
    </h2>
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
