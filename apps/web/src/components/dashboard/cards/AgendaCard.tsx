'use client';
import { ClassificationBadges } from '@/components/chat/ClassificationBadges';

import { Calendar, CalendarDays, Clock3, MapPin, Navigation, NotebookPen } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { BriefingCard } from '../BriefingCard';
import type { CardItemAction } from './CardItemActions';
import { CardItemRow } from './CardItemRow';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { AgendaData, AgendaEventItem, CardSection } from '@/types/briefing';

interface AgendaCardProps {
  section: CardSection<AgendaData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function AgendaCard({ section, isRefreshing, onRefresh, staggerIndex }: AgendaCardProps) {
  const router = useRouter();
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<AgendaData>
      titleKey="dashboard.briefing.cards.agenda.title"
      icon={<Calendar className="h-5 w-5" />}
      tone="violet"
      className="sm:col-span-2"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.agenda.empty"
      onErrorCta={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => (
        <AgendaContent
          data={data}
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onExecute={intent => openChatDeepLink(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

interface AgendaDay {
  key: string;
  label: string | null;
  events: AgendaEventItem[];
}

/** Read the existing machine instant, never guess a day from localized prose. */
function agendaDays(
  events: AgendaEventItem[],
  locale: string,
  timezone: string | undefined
): AgendaDay[] {
  if (!timezone) return [{ key: 'undated', label: null, events }];
  let keyFormatter: Intl.DateTimeFormat;
  let labelFormatter: Intl.DateTimeFormat;
  try {
    keyFormatter = new Intl.DateTimeFormat('en', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    labelFormatter = new Intl.DateTimeFormat(locale, {
      timeZone: timezone,
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    });
  } catch {
    return [{ key: 'undated', label: null, events }];
  }
  const groups = new Map<string, AgendaDay>();
  const undated: AgendaEventItem[] = [];
  const ordered = events
    .map((event, index) => {
      const instant =
        event.start_at && /(?:Z|[+-]\d{2}:\d{2})$/.test(event.start_at)
          ? Date.parse(event.start_at)
          : NaN;
      return { event, index, instant };
    })
    .sort((a, b) => {
      if (!Number.isFinite(a.instant)) return Number.isFinite(b.instant) ? 1 : a.index - b.index;
      if (!Number.isFinite(b.instant)) return -1;
      return a.instant - b.instant || a.index - b.index;
    });
  for (const { event, instant } of ordered) {
    if (!Number.isFinite(instant)) {
      undated.push(event);
      continue;
    }
    const parts = keyFormatter.formatToParts(instant);
    const value = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find(part => part.type === type)?.value;
    const key = `${value('year')}-${value('month')}-${value('day')}`;
    const group = groups.get(key) ?? { key, label: labelFormatter.format(instant), events: [] };
    group.events.push(event);
    groups.set(key, group);
  }
  const result = [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
  if (undated.length) result.push({ key: 'undated', label: null, events: undated });
  return result;
}

/** Mutable timing is presentation, never an event's component identity. */
function agendaEntries(events: AgendaEventItem[]) {
  const occurrences = new Map<string, number>();
  return events.map((event, index) => {
    if (!event.id) return { event, key: `legacy-${index}` };
    const duplicate = occurrences.get(event.id) ?? 0;
    occurrences.set(event.id, duplicate + 1);
    return { event, key: `id-${event.id}-${duplicate}` };
  });
}

function AgendaContent({
  data,
  onOpenChat,
  onExecute,
}: {
  data: AgendaData;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const groups = agendaDays(data.events, i18n.language || 'fr', user?.timezone);
  return (
    <div className="@container space-y-5">
      {groups.map(group => (
        <div key={group.key} className="space-y-4">
          {group.label && (
            <h4 className="flex items-center gap-2 border-b border-border pb-2 text-sm font-medium text-foreground">
              <CalendarDays
                className="size-4 shrink-0 text-violet-700 dark:text-violet-300"
                aria-hidden="true"
              />
              <time dateTime={group.key}>{group.label}</time>
            </h4>
          )}
          <ul className="grid grid-cols-1 gap-x-5 gap-y-2 @min-[32rem]:grid-cols-3" role="list">
            {agendaEntries(group.events).map(({ event, key }) => (
              <AgendaEntry key={key} event={event} onOpenChat={onOpenChat} onExecute={onExecute} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function AgendaEntry({
  event,
  onOpenChat,
  onExecute,
}: {
  event: AgendaEventItem;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t } = useTranslation();
  const intent = t('dashboard.briefing.intents.event', {
    title: event.title,
    time: event.start_local,
  });
  const prepareIntent = t('dashboard.briefing.intents_exec.event_prepare', {
    title: event.title,
    time: event.start_local,
  });
  const actions: CardItemAction[] = [
    { icon: NotebookPen, label: prepareIntent, onSelect: () => onExecute(prepareIntent) },
  ];
  if (event.location) {
    const routeIntent = t('dashboard.briefing.intents_exec.event_route', {
      location: event.location,
    });
    actions.push({ icon: Navigation, label: routeIntent, onSelect: () => onExecute(routeIntent) });
  }
  return (
    <CardItemRow
      ariaLabel={intent}
      tooltip={event.location ? `${event.title}\n${event.location}` : event.title}
      onSelect={() => onOpenChat(intent)}
      actions={actions}
      className="relative border-l border-l-violet-300/50 pl-3 before:absolute before:-left-1 before:top-4 before:size-2 before:rounded-full before:bg-violet-400 @min-[32rem]:border-l-0 @min-[32rem]:border-t @min-[32rem]:border-b-0 @min-[32rem]:pl-0 @min-[32rem]:pt-4 @min-[32rem]:before:left-0 @min-[32rem]:before:-top-1"
      contentClassName="flex flex-col items-start gap-2"
    >
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium tabular-nums text-violet-700 dark:text-violet-300">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="size-3.5 shrink-0" aria-hidden="true" />
          {event.time_range_local ?? event.start_local}
        </span>
        {!event.time_range_local && event.end_local && (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <span aria-hidden="true">–</span>
            <span>{event.end_local}</span>
          </span>
        )}
      </span>
      <span className="line-clamp-3 break-words text-sm font-semibold leading-relaxed text-foreground">
        {event.title}
      </span>
      <ClassificationBadges value={event.classification} />
      {event.location && (
        <span className="flex items-start gap-1.5 text-xs leading-relaxed text-muted-foreground">
          <MapPin
            className="mt-0.5 size-3.5 shrink-0 text-violet-700 dark:text-violet-300"
            aria-hidden="true"
          />
          <span className="line-clamp-2 break-words">{event.location}</span>
        </span>
      )}
    </CardItemRow>
  );
}
