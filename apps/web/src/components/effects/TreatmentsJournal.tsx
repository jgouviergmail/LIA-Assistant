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
import { CheckCircle2, Eye, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  RegisterJournalTitle,
  registerEmptyState,
  registerTotalLabel,
  type RegisterHeadingOverride,
} from '@/components/effects/RegisterJournalChrome';
import { RegisterJournalBody } from '@/components/effects/RegisterJournalBody';
import { RegisterRow } from '@/components/effects/RegisterRow';
import { RegisterFilter } from '@/components/effects/RegisterJournalStates';
import { Badge } from '@/components/ui/badge';
import { useTreatmentsJournal } from '@/hooks/useTreatmentsJournal';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { lifecycleTone } from '@/lib/status-tone';
import type { RegisterOrigin } from '@/types/register-origin';
import type { TreatmentEntry } from '@/types/treatments';

export interface TreatmentsJournalProps {
  /** Current URL locale segment (drives date/time formatting). */
  lng: string;
  /**
   * Which authorships to read. Defaults to everything so an existing
   * caller keeps its behaviour; the tabs pass `mine` or `initiative`.
   */
  origin?: RegisterOrigin;
  /**
   * Wording for this reading, when a container names the list better than the
   * register does. The initiative tab stacks both registers under its own
   * headings; without this each list carried TWO titles — the tab's and the
   * journal's own — over one set of rows (reported from the dev instance,
   * 2026-09-07). Omitted, the journal names itself, as it does on its own tab.
   */
  heading?: RegisterHeadingOverride;
}

export function TreatmentsJournal({ lng, origin = 'all', heading }: TreatmentsJournalProps) {
  const { t, i18n } = useTranslation();
  const [tool, setTool] = useState<string | undefined>(undefined);
  const state = useTreatmentsJournal(tool, origin);
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
      <RegisterJournalTitle
        icon={Eye}
        title={t('treatments.journal.title')}
        description={t('treatments.journal.description')}
        heading={heading}
        exportKind="consultations"
        origin={origin}
        refreshLabel={t('treatments.journal.refresh')}
        onRefresh={refetch}
        firstLoad={firstLoad}
        loading={loading}
      />

      <RegisterJournalBody<TreatmentEntry, FoldedTreatment>
        state={state}
        skeletonSlot="treatments-skeleton"
        errorMessage={t('treatments.journal.error')}
        retryLabel={t('treatments.journal.retry')}
        totalLabel={registerTotalLabel(t, 'treatments.journal.total', total)}
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
        empty={registerEmptyState(t, {
          icon: Eye,
          prefix: 'treatments.journal',
          filtered,
          lng,
        })}
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

  return (
    <RegisterRow
      icon={failed ? XCircle : CheckCircle2}
      failed={failed}
      headline={t(`treatments.domains.${entry.domain}`, {
        defaultValue: t('treatments.domains.unknown'),
      })}
      when={when}
      dateTime={entry.occurred_at}
      headlineBadges={
        entry.repeats > 1 ? (
          <Badge variant="secondary">
            {t('treatments.journal.repeats', { count: entry.repeats })}
          </Badge>
        ) : undefined
      }
      detailBadges={
        // ALWAYS, the way the action register always states its status. Shown
        // only on failure, a successful read said nothing at all — so a reader
        // could not tell « it answered » from « nothing was recorded », while
        // the neighbouring tab spelled its outcome out on every row (owner
        // report on display homogeneity, 2026-09-07).
        <Badge variant={lifecycleTone(failed ? 'failed' : 'succeeded')}>
          {t(`treatments.journal.outcome.${failed ? 'failed' : 'ok'}`)}
        </Badge>
      }
      capability={entry.tool_name}
      durationMs={entry.total_ms}
      source={entry.source}
    />
  );
}
