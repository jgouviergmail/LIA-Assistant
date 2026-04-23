'use client';

import { Cake } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import type { BirthdaysData, CardSection } from '@/types/briefing';

interface BirthdaysCardProps {
  section: CardSection<BirthdaysData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function BirthdaysCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: BirthdaysCardProps) {
  return (
    <BriefingCard<BirthdaysData>
      titleKey="dashboard.briefing.cards.birthdays.title"
      icon={<Cake className="h-5 w-5" />}
      tone="rose"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.birthdays.empty"
      renderContent={data => <BirthdaysContent data={data} />}
      staggerIndex={staggerIndex}
    />
  );
}

function BirthdaysContent({ data }: { data: BirthdaysData }) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-2" role="list">
      {data.items.map((birthday, index) => (
        <li key={index} className="flex items-baseline justify-between gap-2 text-sm">
          <span className="text-foreground/90 truncate font-medium">
            {birthday.contact_name}
            {birthday.age_at_next !== null && (
              <span className="text-muted-foreground/70 font-normal ml-1">
                ({birthday.age_at_next})
              </span>
            )}
          </span>
          <span className="shrink-0 text-xs font-semibold text-rose-600 dark:text-rose-300 tabular-nums">
            {birthday.days_until === 0
              ? t('dashboard.briefing.cards.birthdays.today')
              : t('dashboard.briefing.cards.birthdays.in_days', {
                  count: birthday.days_until,
                })}
          </span>
        </li>
      ))}
    </ul>
  );
}
