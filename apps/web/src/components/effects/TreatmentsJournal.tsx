'use client';

/**
 * TreatmentsJournal — what LIA looked at (ADR-263, lot 4).
 *
 * The companion of `EffectsJournal`, and a SEPARATE list by decision: the two
 * registers count different things, and a reader able to add their totals
 * would get a number that means nothing. One answers "what did the assistant
 * do"; this one answers "what did it look at" — the question a person actually
 * asks when they wonder what an assistant knows about them.
 *
 * The headline is the DOMAIN, resolved from `treatments.domains.*` in the
 * reader's current language; the capability name sits beside it as the
 * technical half. A consultation records nothing of what was asked, so there
 * is nothing else to show and nothing to mask.
 *
 * The states, the emptiness rules and the load-more footer live in
 * `RegisterJournalBody`, shared with the action register: what stays here is
 * what belongs to THIS register — its filter, and how one row reads.
 */

import { useMemo, useState } from 'react';
import { CheckCircle2, Eye, RefreshCw, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { RegisterExportButton } from '@/components/effects/RegisterExportButton';
import { RegisterJournalBody } from '@/components/effects/RegisterJournalBody';
import { RegisterFilter, RegisterHeader } from '@/components/effects/RegisterJournalStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTreatmentsJournal } from '@/hooks/useTreatmentsJournal';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { TreatmentEntry } from '@/types/treatments';

export interface TreatmentsJournalProps {
  /** Current URL locale segment (drives date/time formatting). */
  lng: string;
}

export function TreatmentsJournal({ lng }: TreatmentsJournalProps) {
  const { t, i18n } = useTranslation();
  const [tool, setTool] = useState<string | undefined>(undefined);
  const state = useTreatmentsJournal(tool);
  const { entries, total, firstLoad, loading, refetch } = state;

  const locale = getIntlLocale(i18n.language as Language);
  const timeFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }),
    [locale]
  );
  const dayFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long' }),
    [locale]
  );

  // Offered from what the reader can actually see, PLUS whatever is currently
  // selected. Deriving the list from the visible rows alone is a dead end: a
  // filter that matches nothing empties the very list the filter buttons are
  // built from, so the controls vanish and the reader is stranded on "no
  // match" with no way back to "all".
  // Memoised on `entries` itself, not on a `?? []` fallback — that expression
  // builds a NEW array every render and would defeat the memo.
  const capabilities = useMemo(() => {
    const names = new Set((entries ?? []).map(entry => entry.tool_name));
    if (tool !== undefined) names.add(tool);
    return [...names].sort();
  }, [entries, tool]);
  const filtered = tool !== undefined;
  // The same rule as the action register — one rule, two tabs that start at
  // the same height.
  const showFilter = (entries?.length ?? 0) > 0 || filtered;
  // One definition of "which day is this row on", shared by the fold and the
  // section split: two spellings would let a fold merge across a boundary the
  // headings then draw.
  const dayOfEntry = (entry: { occurred_at: string }): string =>
    dayFormat.format(new Date(entry.occurred_at));

  return (
    <section className="space-y-6">
      <RegisterHeader
        actions={
          <>
            <RegisterExportButton register="consultations" />
            <Button variant="outline" size="sm" onClick={refetch} disabled={firstLoad}>
              <RefreshCw
                className={loading && !firstLoad ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
                aria-hidden="true"
              />
              {t('treatments.journal.refresh')}
            </Button>
          </>
        }
      >
        <h2 className="flex items-center gap-2 text-xl font-bold">
          <Eye className="h-5 w-5 text-primary" aria-hidden="true" />
          {t('treatments.journal.title')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('treatments.journal.description')}</p>
      </RegisterHeader>

      <RegisterJournalBody<TreatmentEntry, FoldedTreatment>
        state={state}
        skeletonSlot="treatments-skeleton"
        errorMessage={t('treatments.journal.error')}
        retryLabel={t('treatments.journal.retry')}
        totalLabel={
          total === undefined ? undefined : t('treatments.journal.total', { count: total })
        }
        filters={
          showFilter ? (
            <RegisterFilter<string | undefined>
              label={t('treatments.journal.filter_label')}
              tokens={[undefined, ...capabilities]}
              selected={tool}
              onSelect={setTool}
              renderToken={token => token ?? t('treatments.journal.all_capabilities')}
              keyOf={token => token ?? '__all__'}
            />
          ) : undefined
        }
        empty={{
          icon: Eye,
          title: t(
            filtered ? 'treatments.journal.empty_filtered_title' : 'treatments.journal.empty_title'
          ),
          description: t(
            filtered
              ? 'treatments.journal.empty_filtered_description'
              : 'treatments.journal.empty_description'
          ),
          reason: filtered ? 'no-match' : 'no-data',
          action: {
            label: t('treatments.journal.empty_action'),
            href: `/${lng}/dashboard/chat`,
          },
        }}
        loadMoreLabel={t('treatments.journal.load_more')}
        dayOf={dayOfEntry}
        itemsOf={entries => foldRepeats(entries, dayOfEntry)}
        renderRow={item => (
          <TreatmentRow
            key={item.id}
            item={item}
            when={timeFormat.format(new Date(item.occurred_at))}
          />
        )}
      />
    </section>
  );
}

/** A consultation, or a run of identical ones folded into one line. */
export interface FoldedTreatment extends TreatmentEntry {
  /** How many identical calls this line stands for. 1 for a lone call. */
  repeats: number;
  /** Their durations added up — a fold must not report one and hide four. */
  total_ms: number;
}

/**
 * Fold CONSECUTIVE identical consultations into one line.
 *
 * Measured 2026-09-04 on the dev instance: a single ReAct turn asked the
 * mailbox five times, and the journal printed five identical rows. The
 * register was right — the loop really did call five times — but five
 * identical lines read as noise, and the one fact worth seeing (it happened
 * five times) was the one the reader had to count by hand.
 *
 * Three conditions, and each rules out a way a fold could lie:
 *
 * - **consecutive**, so the list's chronological order — which is its meaning —
 *   is preserved rather than re-bucketed;
 * - **same outcome**, so a failure never hides inside a run of successes;
 * - **same DAY**, so a line never stands for calls that happened on two days
 *   while carrying one day's timestamp. Found by a test: without it, three
 *   entries spanning two days folded into one and the journal showed a single
 *   day heading for a two-day span.
 *
 * The exact server-side total above the list is untouched, so nothing is
 * hidden, only said once.
 */
export function foldRepeats(
  entries: TreatmentEntry[],
  dayOf: (entry: TreatmentEntry) => string
): FoldedTreatment[] {
  const folded: FoldedTreatment[] = [];
  let lastDay: string | undefined;
  for (const entry of entries) {
    const day = dayOf(entry);
    const last = folded[folded.length - 1];
    if (
      last &&
      day === lastDay &&
      last.tool_name === entry.tool_name &&
      last.outcome === entry.outcome
    ) {
      last.repeats += 1;
      last.total_ms += entry.duration_ms;
      continue;
    }
    folded.push({ ...entry, repeats: 1, total_ms: entry.duration_ms });
    lastDay = day;
  }
  return folded;
}

/** One capability, or every capability. The filter travels to the server. */

interface TreatmentRowProps {
  item: FoldedTreatment;
  when: string;
}

function TreatmentRow({ item: entry, when }: TreatmentRowProps) {
  const { t } = useTranslation();
  const failed = entry.outcome === 'failed';
  const Icon = failed ? XCircle : CheckCircle2;

  return (
    <li className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
      <span
        className={cn(
          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          failed ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary'
        )}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="min-w-0 break-words text-sm font-semibold text-foreground">
            {t(`treatments.domains.${entry.domain}`, {
              defaultValue: t('treatments.domains.unknown'),
            })}
          </span>
          <time dateTime={entry.occurred_at} className="text-xs text-muted-foreground">
            {when}
          </time>
          {entry.repeats > 1 && (
            <Badge variant="secondary">
              {t('treatments.journal.repeats', { count: entry.repeats })}
            </Badge>
          )}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1.5">
          {failed && <Badge variant="destructive">{t('treatments.journal.outcome.failed')}</Badge>}
          <span className="min-w-0 break-words font-mono text-xs text-muted-foreground">
            {entry.tool_name}
          </span>
          <span className="text-xs text-muted-foreground">
            {t('treatments.journal.duration', { ms: entry.total_ms })}
          </span>
          <span className="text-xs text-muted-foreground">
            {t(`effects.journal.source.${entry.source}`)}
          </span>
        </span>
      </span>
    </li>
  );
}
