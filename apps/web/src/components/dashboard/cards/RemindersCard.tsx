'use client';

import { Bell } from 'lucide-react';
import { BriefingCard } from '../BriefingCard';
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
  return (
    <BriefingCard<RemindersData>
      titleKey="dashboard.briefing.cards.reminders.title"
      icon={<Bell className="h-5 w-5" />}
      tone="amber"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.reminders.empty"
      renderContent={data => <RemindersContent data={data} />}
      staggerIndex={staggerIndex}
    />
  );
}

function RemindersContent({ data }: { data: RemindersData }) {
  return (
    <ul className="space-y-3" role="list">
      {data.items.map((reminder, index) => (
        <li key={index} className="flex flex-col gap-0.5 leading-tight">
          <span className="text-xs font-semibold text-amber-700 dark:text-amber-300 tabular-nums">
            {reminder.trigger_at_local}
          </span>
          <span className="text-sm text-foreground/90 line-clamp-2 leading-snug">
            {reminder.content}
          </span>
        </li>
      ))}
    </ul>
  );
}
