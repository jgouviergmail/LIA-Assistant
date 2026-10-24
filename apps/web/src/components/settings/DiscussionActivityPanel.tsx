'use client';

import { useId, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  MessageCircleQuestion,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Badge } from '@/components/ui/badge';
import { UsageLine, meterFigures } from '@/components/ui/usage-line';
import { formatNumber } from '@/lib/format';
import { lifecycleTone } from '@/lib/status-tone';
import { discussionActivitySchema, type DiscussionActivity } from '@/types/proactive-discussions';

type Budget = DiscussionActivity['budget'];
type Awaiting = NonNullable<DiscussionActivity['awaiting_reply']>;
type Run = NonNullable<DiscussionActivity['last_run']>;
type RunStats = NonNullable<Run['stats']>;

function moment(value: string, lng: Language): string {
  return new Date(value).toLocaleString(getIntlLocale(lng), {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

/** When a run ended, or started while it still runs, as a machine-readable date. */
function RunEnd({ run, lng }: { run: Run; lng: Language }) {
  const value = run.settled_at ?? run.claimed_at;
  return <time dateTime={value}>{moment(value, lng)}</time>;
}

/** What a run read and interpreted, in the order the work happens: counts only. */
function figures(stats: RunStats): readonly (readonly [string, number])[] {
  return [
    ['pages', Object.values(stats.pages).reduce((total, value) => total + value, 0)],
    ['facts', stats.facts_read],
    ['admitted', stats.facts_admitted],
    ['offered', stats.facts_offered],
    ['calls', stats.context_calls],
    ['items', stats.items],
  ];
}

/** One dated fact: its icon and label above, its value below. */
function DatedFact({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-primary" />
        {label}
      </dt>
      <dd className="flex flex-wrap items-center gap-2 text-sm font-medium tabular-nums">
        {children}
      </dd>
    </div>
  );
}

/** When the context was last rebuilt (left), then last updated by any run (right). */
function ContextDates({
  lng,
  rebuild,
  update,
}: {
  lng: Language;
  rebuild: Run | null;
  update: Run | null;
}) {
  const { t } = useTranslation(lng);
  if (!rebuild && !update) return null;
  return (
    <dl className="grid gap-3 p-3 @min-[28rem]:grid-cols-2">
      {rebuild && (
        <DatedFact icon={RefreshCw} label={t('discussions.activity.rebuilt_at')}>
          <RunEnd run={rebuild} lng={lng} />
          <Badge variant={lifecycleTone(rebuild.state)} size="sm">
            {t(`discussions.rebuild_states.${rebuild.state}`)}
          </Badge>
        </DatedFact>
      )}
      {update && (
        <DatedFact icon={CalendarClock} label={t('discussions.activity.updated_at')}>
          <RunEnd run={update} lng={lng} />
        </DatedFact>
      )}
    </dl>
  );
}

/** The last run: its kind and end, why it ended, what it read and what it cost. */
function LastRunDetails({ lng, run }: { lng: Language; run: Run }) {
  const { t } = useTranslation(lng);
  const titleId = useId();
  return (
    // Its own container: the figures take as many columns as THIS width holds.
    <section aria-labelledby={titleId} className="@container min-w-0 space-y-3 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h4 id={titleId} className="flex items-center gap-2 text-sm font-medium">
          <Activity aria-hidden="true" className="h-4 w-4 shrink-0 text-primary" />
          {t('discussions.activity.last_run')}
        </h4>
        {/* The kind and the date wrap together, under the title when it is narrow. */}
        <span className="flex flex-wrap items-center gap-2">
          <Badge variant="default">{t(`discussions.run_kinds.${run.kind}`)}</Badge>
          <span className="text-xs text-muted-foreground tabular-nums">
            <RunEnd run={run} lng={lng} />
          </span>
        </span>
      </div>
      {run.reason && <p className="text-sm">{t(`discussions.activity.reason.${run.reason}`)}</p>}
      {run.stats && (
        // Two columns hold the longest label of the six languages whole; three
        // and six only once the width does, never a word cut in its middle.
        <dl className="grid grid-cols-2 gap-2 @min-[20rem]:grid-cols-3 @min-[40rem]:grid-cols-6">
          {figures(run.stats).map(([key, value]) => (
            // The label is read first, the figure is seen first.
            // A panel inside the card: the background alternates, and it
            // draws its border like every panel (owner rule 2026-10-21).
            <div
              key={key}
              className="flex min-w-0 flex-col-reverse justify-end gap-0.5 rounded-md border bg-background px-2.5 py-2"
            >
              <dt className="break-words text-xs leading-tight text-muted-foreground">
                {t(`discussions.activity.figures.${key}`)}
              </dt>
              <dd className="text-base font-semibold leading-tight tabular-nums">
                {formatNumber(value, lng)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {run.stats && run.stats.proposals_refused > 0 && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {t('discussions.activity.proposals_refused', { count: run.stats.proposals_refused })}
        </p>
      )}
      {run.usage && (
        <UsageLine
          figures={meterFigures(run.usage)}
          cost={run.usage.cost_eur}
          decimals={6}
          className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs tabular-nums"
        />
      )}
    </section>
  );
}

/** The first ceiling that stops a run now, in one plain sentence. */
function CeilingNotice({ lng, budget }: { lng: Language; budget: Budget }) {
  const { t } = useTranslation(lng);
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
    >
      <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
      <span className="min-w-0">
        {t(`discussions.ceiling.${budget.reached}`, {
          date: budget.resets_at ? moment(budget.resets_at, lng) : '',
        })}
      </span>
    </p>
  );
}

/** The opening still awaiting a reply, which holds the next one back: since and until when. */
function AwaitingReplyNotice({ lng, awaiting }: { lng: Language; awaiting: Awaiting }) {
  const { t } = useTranslation(lng);
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm"
    >
      <MessageCircleQuestion aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <span className="min-w-0">
        {t('discussions.activity.awaiting_reply', {
          since: moment(awaiting.since, lng),
          until: moment(awaiting.until, lng),
        })}
      </span>
    </p>
  );
}

/**
 * First — only when one stops LIA — the ceiling reached, then an opening still
 * awaiting a reply; then when the context was last rebuilt and last updated, and
 * the last run with its own figures. As measured.
 */
export function DiscussionActivityPanel({
  lng,
  activity,
}: {
  lng: Language;
  activity: DiscussionActivity | undefined;
}) {
  const parsed = discussionActivitySchema.safeParse(activity);
  if (!parsed.success) return null;
  const {
    last_rebuild: rebuild,
    last_update: update,
    last_run: run,
    budget,
    awaiting_reply: awaiting,
  } = parsed.data;
  const ceiling = budget.configured && budget.reached !== null;
  const dated = Boolean(rebuild || update || run);
  if (!dated && !ceiling && !awaiting) return null;
  return (
    <div className="min-w-0 space-y-3">
      {ceiling && <CeilingNotice lng={lng} budget={budget} />}
      {awaiting && <AwaitingReplyNotice lng={lng} awaiting={awaiting} />}
      {dated && (
        <div className="@container min-w-0 divide-y rounded-lg border bg-card">
          <ContextDates lng={lng} rebuild={rebuild} update={update} />
          {run && <LastRunDetails lng={lng} run={run} />}
        </div>
      )}
    </div>
  );
}
