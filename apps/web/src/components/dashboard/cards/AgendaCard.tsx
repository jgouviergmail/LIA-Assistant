'use client';

import { Calendar, MapPin } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { chatDraftHref } from '@/lib/briefing-utils';
import type { AgendaData, CardSection } from '@/types/briefing';

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
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.agenda.empty"
      onErrorCta={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => (
        <AgendaContent data={data} onOpenChat={draft => router.push(chatDraftHref(lng, draft))} />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function AgendaContent({
  data,
  onOpenChat,
}: {
  data: AgendaData;
  onOpenChat: (draft: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-1" role="list">
      {data.events.map((event, index) => {
        // QW-9: click opens the chat prefilled with a "prepare me" intent.
        const intent = t('dashboard.briefing.intents.event', {
          title: event.title,
          time: event.start_local,
        });
        return (
          <li key={index}>
            <button
              type="button"
              onClick={() => onOpenChat(intent)}
              aria-label={intent}
              className="w-full text-left flex items-start gap-2.5 rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {/* Time column: start (bold) + end (smaller, dimmed) */}
              <span className="flex flex-col items-start tabular-nums shrink-0 leading-tight">
                <span className="text-sm font-bold text-violet-700 dark:text-violet-300">
                  {event.start_local}
                </span>
                {event.end_local && (
                  <span className="text-[11px] text-muted-foreground">{event.end_local}</span>
                )}
              </span>
              {/* Title + optional location */}
              <span className="flex-1 min-w-0 flex flex-col gap-0.5">
                <span className="text-sm text-foreground/90 truncate leading-tight">
                  {event.title}
                </span>
                {event.location && (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground truncate">
                    <MapPin className="h-3 w-3 shrink-0" />
                    {event.location}
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
