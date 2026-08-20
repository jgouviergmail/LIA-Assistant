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

import { useMemo } from 'react';
import {
  AlertTriangle,
  Bell,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  CircleDot,
  History,
  RefreshCw,
  Repeat,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useActivityTimeline } from '@/hooks/useActivityTimeline';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
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
  locale: string
): { day: string; items: ActivityEvent[] }[] {
  const dayFormat = new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
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
  const { t, i18n } = useTranslation();
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
  } = useActivityTimeline();

  const locale = getIntlLocale(i18n.language as Language);
  const timeFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }),
    [locale]
  );
  const groups = useMemo(
    () => (events ? groupByLocalDay(events, locale) : []),
    [events, locale]
  );
  const visibleTotals = totals.filter(item => item.total > 0);
  const anyTruncated = visibleTotals.some(item => item.truncated);

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <History className="h-6 w-6 text-primary" aria-hidden="true" />
            {t('activity.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('activity.subtitle', { days: windowDays ?? 30 })}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refetch} disabled={firstLoad}>
          <RefreshCw
            className={loading && !firstLoad ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            aria-hidden="true"
          />
          {t('activity.refresh')}
        </Button>
      </header>

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
          {failedKinds.length > 0 && (
            <Alert variant="warning">{t('activity.partial_warning')}</Alert>
          )}

          {visibleTotals.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {visibleTotals.map(item => (
                <Badge key={item.kind} variant="default">
                  {t(`activity.kinds.${item.kind}`, { count: item.total })}
                </Badge>
              ))}
              {anyTruncated && (
                <span className="text-xs text-muted-foreground">
                  {t('activity.truncated_hint')}
                </span>
              )}
            </div>
          )}

          {events !== undefined && events.length === 0 ? (
            <EmptyState
              variant="page"
              icon={History}
              title={t('activity.empty_title')}
              description={t('activity.empty_description')}
              reason="no-data"
              action={{
                label: t('activity.empty_action'),
                href: settingsSectionHref(lng, 'heartbeat'),
              }}
            />
          ) : (
            <div className="space-y-6">
              {groups.map(group => (
                <div key={group.day}>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {group.day}
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
            <span className="text-xs text-muted-foreground">
              {t('activity.status_expired')}
            </span>
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
