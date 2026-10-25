'use client';

/**
 * The relationship on one line of time (owner request 2026-10-24).
 *
 * The card's dated records — commitments, calls, memories, relayed messages,
 * text messages — merged by date, newest first, a page at a time, with the
 * mail and the meetings the card already read woven in where its pages cover
 * them; the meetings still to come lead, apart. Folded by default like every
 * section, and read on its FIRST opening only: a folded timeline costs no
 * request. The count on the toggle is every row the timeline holds once read
 * to its end — the card's own exact totals plus the mail and meetings it
 * places — so the index adds up the numbers the sections show (ADR-185).
 *
 * A row is titled by WHEN it happened (`RelationWhen`), its kind written as
 * text — no icon leads a line — and its words 6px below (`SectionRowTitle`).
 */

import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, History, Loader2 } from 'lucide-react';
import type { TFunction } from 'i18next';

import {
  CollapsibleSection,
  SectionBadge,
  SectionRow,
  SectionRowTitle,
  SectionRows,
} from '@/components/relations/CollapsibleSection';
import { RelationWhen } from '@/components/relations/RelationWhen';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { TimelineDayGroup, TimelineGroup } from '@/components/ui/timeline-group';
import { useRelationTimeline } from '@/hooks/useRelationTimeline';
import type { RelationContext, RelationDetail } from '@/hooks/useRelations';
import {
  entryOf,
  groupByDay,
  mergeEntries,
  providerEntries,
  type ProviderEntries,
  type TimelineEntry,
} from '@/lib/relations/timeline';
import { cn } from '@/lib/utils';

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const { t } = useTranslation();
  return (
    <SectionRow>
      <SectionRowTitle>
        <span className="text-px-11 font-semibold text-foreground">
          {t(`relations.timeline.kind.${entry.kind}`)}
        </span>
        <RelationWhen start={entry.at} />
      </SectionRowTitle>
      {/* Worded as its section words it: only a relayed message past its
          retention keeps no text, and the card says so the same way. */}
      <p
        className={cn(
          'line-clamp-4 whitespace-pre-line [overflow-wrap:anywhere]',
          entry.text ? 'text-sm text-foreground/90' : 'text-xs italic text-muted-foreground'
        )}
      >
        {entry.text || t('relations.peer_message_no_content')}
      </p>
      {entry.detail && (
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground [overflow-wrap:anywhere]">
          {entry.detail}
        </p>
      )}
    </SectionRow>
  );
}

function windowsNote(t: TFunction, context: RelationContext | null): string | null {
  if (!context) return null;
  const parts: string[] = [];
  if (context.email_window_days > 0)
    parts.push(t('relations.emails_window', { count: context.email_window_days }));
  if (context.window_days > 0)
    parts.push(t('relations.events_window', { count: context.window_days }));
  return parts.length > 0 ? parts.join(' ') : null;
}

function TimelineBody({
  name,
  detail,
  context,
  provider,
  lng,
}: {
  name: string;
  detail: RelationDetail;
  context: RelationContext | null;
  provider: ProviderEntries;
  lng: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  // Follows the card: every time it reads the person again, so does the timeline.
  const timeline = useRelationTimeline(name, detail);
  if (timeline.loading) {
    return <Skeleton className="h-24 w-full rounded-xl" label={t('relations.timeline.loading')} />;
  }
  if (timeline.error) {
    return <p className="text-sm text-destructive">{t('relations.timeline.error')}</p>;
  }
  const entries = mergeEntries(timeline.items.map(entryOf), provider.past, !timeline.hasMore);
  if (entries.length === 0 && provider.upcoming.length === 0) {
    return <EmptyState icon={History} description={t('relations.timeline.empty')} />;
  }
  const note = windowsNote(t, context);
  return (
    <div className="space-y-4" aria-busy={timeline.loadingMore}>
      {provider.upcoming.length > 0 && (
        <TimelineGroup
          headingId={`${id}-upcoming`}
          heading={t('relations.event_upcoming')}
          icon={CalendarClock}
          level={4}
        >
          <SectionRows>
            {provider.upcoming.map(entry => (
              <TimelineRow key={entry.key} entry={entry} />
            ))}
          </SectionRows>
        </TimelineGroup>
      )}
      {groupByDay(entries, lng).map(day => (
        <TimelineDayGroup
          key={day.key}
          headingId={`${id}-${day.key}`}
          heading={day.label}
          dayNumber={day.dayNumber}
          month={day.month}
          level={4}
          // Framed inside the section's card: the page's ground, so the two alternate.
          surface="background"
        >
          <div className="px-3">
            <SectionRows>
              {day.entries.map(entry => (
                <TimelineRow key={entry.key} entry={entry} />
              ))}
            </SectionRows>
          </div>
        </TimelineDayGroup>
      ))}
      {timeline.moreFailed && (
        <p role="alert" className="text-sm text-destructive">
          {t('relations.timeline.more_error')}
        </p>
      )}
      {timeline.hasMore && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => void timeline.loadMore()}
          aria-disabled={timeline.loadingMore}
        >
          {timeline.loadingMore && (
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          )}
          {t('relations.timeline.older')}
        </Button>
      )}
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function RelationTimelineSection({
  name,
  detail,
  context,
  lng,
}: {
  name: string;
  detail: RelationDetail;
  context: RelationContext | null;
  lng: string;
}) {
  const { t } = useTranslation();
  // Latched on the first opening: folding it again keeps what was read.
  const [opened, setOpened] = useState(false);
  const provider = providerEntries(context);
  const count =
    detail.open_loops_total +
    detail.recent_calls_total +
    detail.memories_total +
    detail.peer_messages_total +
    (detail.sms_total ?? 0) +
    provider.past.length +
    provider.upcoming.length;
  if (count === 0) return null;
  return (
    <CollapsibleSection
      icon={History}
      title={t('relations.timeline.title')}
      badge={<SectionBadge>{count}</SectionBadge>}
      onOpenChange={open => {
        if (open) setOpened(true);
      }}
    >
      {opened && (
        <TimelineBody
          name={name}
          detail={detail}
          context={context}
          provider={provider}
          lng={lng}
        />
      )}
    </CollapsibleSection>
  );
}
