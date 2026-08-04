'use client';

import { Cake, Gift } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemRow } from './CardItemRow';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
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
  const { i18n } = useTranslation();
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
      renderContent={data => (
        <BirthdaysContent
          data={data}
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onExecute={intent => openChatDeepLink(chatIntentHref(lng, intent))}
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
  const { t } = useTranslation();
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
            align="center"
            contentClassName="flex items-baseline justify-between gap-2 text-sm"
            actions={[
              { icon: Gift, label: messageIntent, onSelect: () => onExecute(messageIntent) },
            ]}
          >
            <span className="text-foreground/90 truncate font-medium">
              {birthday.contact_name}
              {birthday.age_at_next !== null && (
                <span className="text-muted-foreground font-normal ml-1">
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
          </CardItemRow>
        );
      })}
    </ul>
  );
}
