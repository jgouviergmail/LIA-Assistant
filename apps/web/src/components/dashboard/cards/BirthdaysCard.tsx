'use client';

import { Cake, Gift } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemRow } from './CardItemRow';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { useDashboardChat } from '../DashboardNavigation';
import type { BirthdaysData, BriefingWindows, CardSection } from '@/types/briefing';

interface BirthdaysCardProps {
  section: CardSection<BirthdaysData>;
  /** The windows the API built the cards with — the empty state names the horizon. */
  windows: BriefingWindows;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function BirthdaysCard({
  section,
  windows,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: BirthdaysCardProps) {
  const { i18n } = useTranslation();
  const openChat = useDashboardChat();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<BirthdaysData>
      titleKey="dashboard.briefing.cards.birthdays.title"
      icon={<Cake className="h-5 w-5" />}
      tone="rose"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.birthdays.empty"
      emptyStateValues={{ count: windows.birthdays_horizon_days }}
      renderContent={data => (
        <BirthdaysContent
          data={data}
          onOpenChat={draft => openChat(chatDraftHref(lng, draft))}
          onExecute={intent => openChat(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function BirthdaysContent({
  data,
  onOpenChat,
  onExecute,
}: {
  data: BirthdaysData;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const dateFormat = new Intl.DateTimeFormat(i18n.language || 'fr', {
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  });
  return (
    <ul className="space-y-0.5" role="list">
      {data.items.map((birthday, index) => {
        // QW-9: click opens the chat prefilled with a birthday-message intent.
        const intent = t('dashboard.briefing.intents.birthday', {
          name: birthday.contact_name,
        });
        const messageIntent = t('dashboard.briefing.intents_exec.birthday_message', {
          name: birthday.contact_name,
        });
        return (
          <CardItemRow
            key={index}
            ariaLabel={intent}
            tooltip={birthday.contact_name}
            onSelect={() => onOpenChat(intent)}
            contentClassName="flex flex-col gap-1.5 leading-snug"
            actions={[
              {
                icon: Gift,
                label: messageIntent,
                opensChat: true,
                onSelect: () => onExecute(messageIntent),
              },
            ]}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium text-rose-600 dark:text-rose-300 tabular-nums">
              <Cake className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {birthday.days_until === 0
                ? t('dashboard.briefing.cards.birthdays.today')
                : t('dashboard.briefing.cards.birthdays.in_days', {
                    count: birthday.days_until,
                  })}
            </span>
            <span className="line-clamp-2 break-words text-sm font-semibold text-foreground/90">
              {birthday.contact_name}
            </span>
            <span className="text-xs text-muted-foreground">
              {birthday.age_at_next !== null && (
                <>
                  {t('dashboard.briefing.cards.birthdays.age_next', {
                    count: birthday.age_at_next,
                  })}{' '}
                  ·{' '}
                </>
              )}
              {/* A birthday is a civil month/day, even when its year is unknown.
                  A fixed leap year preserves February 29; UTC prevents a day shift. */}
              {dateFormat.format(new Date(`2000-${birthday.date_iso.slice(-5)}T00:00:00Z`))}
            </span>
          </CardItemRow>
        );
      })}
    </ul>
  );
}
