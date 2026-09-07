'use client';

/**
 * EffectsJournal — the user's own record of what LIA actually did (ADR-263).
 *
 * The activity timeline next door shows what the PROACTIVE subsystems produced
 * (a notification, a journal entry, a detected habit). This one shows what a
 * CAPABILITY performed in the world — an email that left, a light that
 * switched, a task that closed — read straight from the effect register, which
 * is written before the action and closed from its result. That is why it can
 * state a failure or a refusal: nothing here is reconstructed after the fact.
 *
 * The wording is resolved from `label_key` + `values` in the reader's current
 * language, so switching locale re-reads the same rows in the new one.
 *
 * Loading rules (charter): first load → skeleton geometry + one announcement;
 * refetch of a populated list → `aria-busy`, never an unmount; a filter that
 * matches nothing is a DIFFERENT emptiness from a register with no rows.
 */

import { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, ClipboardList, Clock, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  RegisterJournalTitle,
  registerEmptyState,
  registerTotalLabel,
  type RegisterHeadingOverride,
} from '@/components/effects/RegisterJournalChrome';
import { RegisterRow } from '@/components/effects/RegisterRow';
import { RegisterJournalBody } from '@/components/effects/RegisterJournalBody';
import { RegisterFilter } from '@/components/effects/RegisterJournalStates';
import { Badge } from '@/components/ui/badge';
import { useEffectsJournal } from '@/hooks/useEffectsJournal';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { lifecycleTone } from '@/lib/status-tone';
import type { RegisterOrigin } from '@/types/register-origin';
import type { EffectEntry, EffectStatus } from '@/types/effects';

export interface EffectsJournalProps {
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

/** Decorative glyph per outcome — the badge carries the meaning. */
const STATUS_ICONS: Record<EffectStatus, LucideIcon> = {
  succeeded: CheckCircle2,
  failed: XCircle,
  refused: AlertCircle,
  claimed: Clock,
  abandoned: AlertCircle,
};

/** Filter tokens offered above the list. `all` is the default. */
const STATUS_FILTERS = ['all', 'succeeded', 'failed', 'refused'] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

/** Badge tone per outcome — from the shared vocabulary, never a local map. */
export function EffectsJournal({ lng, origin = 'all', heading }: EffectsJournalProps) {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<StatusFilter>('all');
  // The filter travels to the SERVER, so `total` describes the list on screen
  // and "load more" keeps working under a filter.
  const state = useEffectsJournal(filter === 'all' ? undefined : filter, origin);
  const { total, firstLoad, loading, refetch } = state;
  const unfiltered = filter === 'all';
  // Both registers show their filter under ONE rule: when there is something
  // to filter, or when one is applied so a reader can always get back to
  // « all ». Two rules were how the two tabs came to start at two different
  // heights (reported 2026-09-05).
  const showFilter = (state.entries?.length ?? 0) > 0 || !unfiltered;

  const locale = getIntlLocale(i18n.language as Language);
  // Two formatters, one locale: the row shows a clock, the section shows a
  // day. Both are the READER's, resolved from the URL locale segment.
  const timeFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }),
    [locale]
  );
  const dayFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { weekday: 'long', day: 'numeric', month: 'long' }),
    [locale]
  );

  return (
    <section className="space-y-6">
      <RegisterJournalTitle
        icon={ClipboardList}
        title={t('effects.journal.title')}
        description={t('effects.journal.description')}
        heading={heading}
        exportKind="actions"
        origin={origin}
        refreshLabel={t('effects.journal.refresh')}
        onRefresh={refetch}
        firstLoad={firstLoad}
        loading={loading}
      />

      <RegisterJournalBody<EffectEntry>
        state={state}
        skeletonSlot="effects-skeleton"
        errorMessage={t('effects.journal.error')}
        retryLabel={t('effects.journal.retry')}
        totalLabel={registerTotalLabel(t, 'effects.journal.total', total)}
        // Shown under the same rule as the other register: a filter appears
        // when there is something to filter, or when one is applied so a
        // reader can always get back to « all ». Two rules were how the two
        // tabs came to start at two different heights.
        filters={
          showFilter ? (
            <RegisterFilter<StatusFilter>
              label={t('effects.journal.filter_label')}
              tokens={STATUS_FILTERS}
              selected={filter}
              onSelect={setFilter}
              renderToken={token => t(`effects.journal.status.${token}`)}
              keyOf={token => token}
            />
          ) : undefined
        }
        empty={registerEmptyState(t, {
          icon: ClipboardList,
          prefix: 'effects.journal',
          filtered: !unfiltered,
          lng,
        })}
        loadMoreLabel={t('effects.journal.load_more')}
        dayOf={entry => dayFormat.format(new Date(entry.claimed_at))}
        itemsOf={entries => entries}
        renderRow={entry => (
          <JournalRow
            key={entry.id}
            entry={entry}
            when={timeFormat.format(new Date(entry.claimed_at))}
          />
        )}
      />
    </section>
  );
}

/** One outcome, or every outcome. The filter travels to the server. */

interface JournalRowProps {
  entry: EffectEntry;
  when: string;
}

function JournalRow({ entry, when }: JournalRowProps) {
  const { t } = useTranslation();
  const label = t(entry.label_key, { ...entry.values, defaultValue: '' });

  return (
    <RegisterRow
      icon={STATUS_ICONS[entry.status] ?? AlertCircle}
      failed={entry.status === 'failed'}
      headline={label || t('effects.labels.generic', { tool: entry.tool_name })}
      when={when}
      dateTime={entry.claimed_at}
      detailBadges={
        <Badge variant={lifecycleTone(entry.status)}>
          {t(`effects.journal.status.${entry.status}`)}
        </Badge>
      }
      capability={entry.tool_name}
      durationMs={durationOf(entry)}
      source={entry.source}
    />
  );
}

/**
 * How long the effect took, or `null` while it is still in flight.
 *
 * An effect is CLAIMED before it happens and closed from its result, so a row
 * with no `closed_at` has not finished — showing `0 ms` there would read as
 * "instant" rather than "still running", which is the opposite of what the
 * ledger is for.
 */
function durationOf(entry: EffectEntry): number | null {
  if (!entry.closed_at) return null;
  const elapsed = new Date(entry.closed_at).getTime() - new Date(entry.claimed_at).getTime();
  return Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null;
}
