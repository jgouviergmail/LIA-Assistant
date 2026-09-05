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
import { AlertCircle, CheckCircle2, ClipboardList, Clock, RefreshCw, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { RegisterExportButton } from '@/components/effects/RegisterExportButton';
import { RegisterJournalBody } from '@/components/effects/RegisterJournalBody';
import { RegisterFilter, RegisterHeader } from '@/components/effects/RegisterJournalStates';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useEffectsJournal } from '@/hooks/useEffectsJournal';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { EffectEntry, EffectStatus } from '@/types/effects';

export interface EffectsJournalProps {
  /** Current URL locale segment (drives date/time formatting). */
  lng: string;
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
function toneFor(status: EffectStatus): 'default' | 'destructive' | 'secondary' {
  if (status === 'failed') return 'destructive';
  if (status === 'succeeded') return 'default';
  return 'secondary';
}

export function EffectsJournal({ lng }: EffectsJournalProps) {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<StatusFilter>('all');
  // The filter travels to the SERVER, so `total` describes the list on screen
  // and "load more" keeps working under a filter.
  const state = useEffectsJournal(filter === 'all' ? undefined : filter);
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
      <RegisterHeader
        actions={
          <>
            <RegisterExportButton register="actions" />
            <Button variant="outline" size="sm" onClick={refetch} disabled={firstLoad}>
              <RefreshCw
                className={loading && !firstLoad ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
                aria-hidden="true"
              />
              {t('effects.journal.refresh')}
            </Button>
          </>
        }
      >
        {/* h2: the page shell owns the h1, so the two registers sit at the
            same heading level and the outline stays readable. */}
        <h2 className="flex items-center gap-2 text-xl font-bold">
          <ClipboardList className="h-5 w-5 text-primary" aria-hidden="true" />
          {t('effects.journal.title')}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('effects.journal.description')}</p>
      </RegisterHeader>

      <RegisterJournalBody<EffectEntry>
        state={state}
        skeletonSlot="effects-skeleton"
        errorMessage={t('effects.journal.error')}
        retryLabel={t('effects.journal.retry')}
        totalLabel={total === undefined ? undefined : t('effects.journal.total', { count: total })}
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
        empty={{
          icon: ClipboardList,
          title: t(
            unfiltered ? 'effects.journal.empty_title' : 'effects.journal.empty_filtered_title'
          ),
          description: t(
            unfiltered
              ? 'effects.journal.empty_description'
              : 'effects.journal.empty_filtered_description'
          ),
          reason: unfiltered ? 'no-data' : 'no-match',
          action: {
            label: t('effects.journal.empty_action'),
            href: `/${lng}/dashboard/chat`,
          },
        }}
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
  const Icon = STATUS_ICONS[entry.status] ?? AlertCircle;
  const label = t(entry.label_key, { ...entry.values, defaultValue: '' });

  return (
    <li className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
      <span
        className={cn(
          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          entry.status === 'failed'
            ? 'bg-destructive/10 text-destructive'
            : 'bg-primary/10 text-primary'
        )}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="min-w-0 break-words text-sm font-semibold text-foreground">
            {label || t('effects.labels.generic', { tool: entry.tool_name })}
          </span>
          <time dateTime={entry.claimed_at} className="text-xs text-muted-foreground">
            {when}
          </time>
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-1.5">
          <Badge variant={toneFor(entry.status)}>
            {t(`effects.journal.status.${entry.status}`)}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {t(`effects.journal.source.${entry.source}`)}
          </span>
        </span>
      </span>
    </li>
  );
}
