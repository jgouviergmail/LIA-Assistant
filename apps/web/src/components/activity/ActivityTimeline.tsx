'use client';

/**
 * ActivityTimeline — "what LIA did for you", as one chronological feed.
 *
 * The proactive subsystems (heartbeat, interests, journals, habits, open
 * loops, routines) each keep their own history; this feed is the single
 * place where their work becomes VISIBLE. Events group under local day
 * headings, newest first; the chips above the feed carry the EXACT
 * per-kind totals over the window (ADR-185 — a truncated pool says so).
 *
 * Loading rules (charter): first load → skeleton geometry + one
 * announcement; refetch of a populated feed → `aria-busy`, never an
 * unmount; a failed source → a stated partial-data warning, never silence.
 */

import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bell,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  CircleDot,
  History,
  Repeat,
  Sparkles,
} from '@/lib/icons';
import type { LucideIcon } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { AlertsViewActions } from '@/components/notifications/AlertsViewActions';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { HeadingRule } from '@/components/ui/heading-rule';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { SectionHeader } from '@/components/ui/section-header';
import { Skeleton } from '@/components/ui/skeleton';
import { DEFAULT_ACTIVITY_QUERY, useActivityTimeline } from '@/hooks/useActivityTimeline';
import { useAuth } from '@/hooks/useAuth';
import { useDebounce } from '@/hooks/useDebounce';
import { ActivityListToolbar } from './ActivityListToolbar';
import { ActivityEmptyState, ActivityTotals } from './ActivityStatus';
import { getIntlLocale, type Language } from '@/i18n/settings';
import type { ActivityEvent } from '@/types/activity';

/** Decorative glyph per kind — the label carries the meaning. */
const KIND_ICONS: Record<string, LucideIcon> = {
  heartbeat_notification: Bell,
  interest_notification: Sparkles,
  journal_entry: BookOpen,
  habit_detected: Repeat,
  open_loop_created: CircleDot,
  open_loop_closed: CheckCircle2,
  scheduled_action_run: CalendarClock,
};

export interface ActivityTimelineProps {
  /** Current URL locale segment (drives day/time formatting). */
  lng: string;
}

/** Events grouped by LOCAL day, insertion order preserved (newest first). */
function groupByLocalDay(
  events: ActivityEvent[],
  locale: string,
  timeZone: string | undefined
): { day: string; items: ActivityEvent[] }[] {
  const dayFormat = new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone,
  });
  const groups: { day: string; items: ActivityEvent[] }[] = [];
  for (const item of events) {
    const day = dayFormat.format(new Date(item.occurred_at));
    const last = groups[groups.length - 1];
    if (last && last.day === day) {
      last.items.push(item);
    } else {
      groups.push({ day, items: [item] });
    }
  }
  return groups;
}

export function ActivityTimeline({ lng }: ActivityTimelineProps) {
  const { user } = useAuth();
  return <OwnedActivityTimeline key={user?.id ?? ''} lng={lng} />;
}

function OwnedActivityTimeline({ lng }: ActivityTimelineProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const timeZone = user?.timezone;
  const [criteria, setCriteria] = useState(DEFAULT_ACTIVITY_QUERY);
  const q = useDebounce(criteria.q, 300);
  const {
    events,
    totals,
    failedKinds,
    windowDays,
    hasMore,
    firstLoad,
    loading,
    error,
    loadMore,
    refetch,
  } = useActivityTimeline({ ...criteria, q });
  const filtered = !!(q.trim() || criteria.kind);

  const locale = getIntlLocale(i18n.language as Language);
  const timeFormat = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        hour: '2-digit',
        minute: '2-digit',
        timeZone,
      }),
    [locale, timeZone]
  );
  const groups = useMemo(
    () => (events ? groupByLocalDay(events, locale, timeZone) : []),
    [events, locale, timeZone]
  );

  return (
    <section className="space-y-6">
      {/* The alerts hub's own header: the way back to its two registers —
          received and to follow up — sits exactly where the hub's "Activity
          timeline" button sits, with the journal and the refresh beside it
          (owner request 2026-10-21). */}
      <SectionHeader
        title={t('activity.title')}
        icon={History}
        level={1}
        description={t('activity.subtitle', { days: windowDays ?? 30 })}
        actions={
          <AlertsViewActions
            lng={lng}
            view="activity"
            switchable
            busy={loading}
            onRefresh={refetch}
          />
        }
      />

      <ActivityListToolbar value={criteria} onChange={setCriteria} />

      {error && events === undefined ? (
        <Alert variant="error">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{t('activity.error_description')}</span>
            <Button variant="outline" size="sm" onClick={refetch}>
              {t('activity.retry')}
            </Button>
          </div>
        </Alert>
      ) : firstLoad ? (
        <div data-slot="activity-skeleton" className="space-y-3">
          <LoadingAnnouncement />
          <Skeleton className="h-6 w-40" />
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div aria-busy={loading || undefined} className="space-y-6">
          {error && <Alert variant="warning">{t('activity.refresh_error')}</Alert>}
          {failedKinds.length > 0 && (
            <Alert variant="warning">{t('activity.partial_warning')}</Alert>
          )}

          <ActivityTotals totals={totals} />

          {events !== undefined && events.length === 0 ? (
            <ActivityEmptyState
              lng={lng}
              filtered={filtered}
              failed={failedKinds.length > 0}
              retry={refetch}
              clear={() => setCriteria(DEFAULT_ACTIVITY_QUERY)}
            />
          ) : (
            <div className="space-y-6">
              {groups.map(group => (
                <div key={group.day}>
                  {/* A day is a rubrique: its heading runs on into the hairline
                      every screen draws after one (owner request 2026-10-21). */}
                  <p className="mb-2 flex items-center gap-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {group.day}
                    <HeadingRule />
                  </p>
                  <ul className="space-y-2">
                    {group.items.map(item => (
                      <TimelineRow
                        key={`${item.kind}:${item.ref_id}`}
                        item={item}
                        time={timeFormat.format(new Date(item.occurred_at))}
                        label={t(`activity.rows.${item.kind}`)}
                      />
                    ))}
                  </ul>
                </div>
              ))}

              {hasMore && (
                <div className="flex justify-center">
                  <Button onClick={loadMore} isLoading={loading && !firstLoad}>
                    {t('activity.load_more')}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

interface TimelineRowProps {
  item: ActivityEvent;
  time: string;
  label: string;
}

function TimelineRow({ item, time, label }: TimelineRowProps) {
  // `dateTime` gives assistive tech and crawlers the machine-readable
  // instant behind the localized short time.
  const { t } = useTranslation();
  const Icon = KIND_ICONS[item.kind] ?? AlertTriangle;

  return (
    <li className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm font-semibold text-foreground">{label}</span>
          <time dateTime={item.occurred_at} className="text-xs text-muted-foreground">
            {time}
          </time>
          {item.kind === 'open_loop_closed' && item.status === 'expired' && (
            <span className="text-xs text-muted-foreground">{t('activity.status_expired')}</span>
          )}
        </span>
        {item.text && (
          <span className="mt-0.5 line-clamp-2 break-words text-sm text-muted-foreground">
            {item.text}
          </span>
        )}
      </span>
    </li>
  );
}
