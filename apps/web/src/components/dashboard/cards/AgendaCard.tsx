'use client';

import { Calendar, MapPin } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import type { AgendaData, CardSection } from '@/types/briefing';

interface AgendaCardProps {
  section: CardSection<AgendaData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function AgendaCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: AgendaCardProps) {
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
      renderContent={data => <AgendaContent data={data} />}
      staggerIndex={staggerIndex}
    />
  );
}

function AgendaContent({ data }: { data: AgendaData }) {
  return (
    <ul className="space-y-2.5" role="list">
      {data.events.map((event, index) => (
        <li key={index} className="flex items-start gap-2.5">
          {/* Time column: start (bold) + end (smaller, dimmed) */}
          <div className="flex flex-col items-start tabular-nums shrink-0 leading-tight">
            <span className="text-sm font-bold text-violet-700 dark:text-violet-300">
              {event.start_local}
            </span>
            {event.end_local && (
              <span className="text-[11px] text-muted-foreground/80">
                {event.end_local}
              </span>
            )}
          </div>
          {/* Title + optional location */}
          <div className="flex-1 min-w-0 flex flex-col gap-0.5">
            <span className="text-sm text-foreground/90 truncate leading-tight">
              {event.title}
            </span>
            {event.location && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground/80 truncate">
                <MapPin className="h-3 w-3 shrink-0" />
                {event.location}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
