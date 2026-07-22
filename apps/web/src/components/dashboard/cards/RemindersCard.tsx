'use client';

import { Bell } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { chatDraftHref } from '@/lib/briefing-utils';
import type { CardSection, RemindersData } from '@/types/briefing';

interface RemindersCardProps {
  section: CardSection<RemindersData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function RemindersCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: RemindersCardProps) {
  const router = useRouter();
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<RemindersData>
      titleKey="dashboard.briefing.cards.reminders.title"
      icon={<Bell className="h-5 w-5" />}
      tone="amber"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.reminders.empty"
      renderContent={data => (
        <RemindersContent data={data} onOpenChat={() => router.push(chatDraftHref(lng))} />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function RemindersContent({ data, onOpenChat }: { data: RemindersData; onOpenChat: () => void }) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-1.5" role="list">
      {data.items.map((reminder, index) => (
        <li key={index}>
          {/* QW-9: reminders open the chat plainly (product decision — the
              reminder will fire on its own; no prefilled intent needed). */}
          <button
            type="button"
            onClick={onOpenChat}
            aria-label={t('dashboard.briefing.intents.reminder_aria')}
            className="w-full text-left flex flex-col gap-0.5 leading-tight rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 tabular-nums">
              {reminder.trigger_at_local}
            </span>
            <span className="text-sm text-foreground/90 line-clamp-2 leading-snug">
              {reminder.content}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
