'use client';

import { Mail, Reply, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemActions } from './CardItemActions';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import type { CardSection, MailsData } from '@/types/briefing';

interface MailsCardProps {
  section: CardSection<MailsData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

export function MailsCard({ section, isRefreshing, onRefresh, staggerIndex }: MailsCardProps) {
  const router = useRouter();
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<MailsData>
      titleKey="dashboard.briefing.cards.mails.title"
      icon={<Mail className="h-5 w-5" />}
      tone="emerald"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.mails.empty"
      onErrorCta={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => (
        <MailsContent
          data={data}
          onOpenChat={draft => router.push(chatDraftHref(lng, draft))}
          onExecute={intent => router.push(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function MailsContent({
  data,
  onOpenChat,
  onExecute,
}: {
  data: MailsData;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-bold tabular-nums text-emerald-700 dark:text-emerald-300 tracking-tight">
          {data.total_unread_today}
        </span>
        <span className="text-sm text-muted-foreground">
          {t('dashboard.briefing.cards.mails.unread_label', { count: data.total_unread_today })}
        </span>
      </div>
      <ul className="space-y-1.5" role="list">
        {data.items.map((mail, index) => {
          // QW-9: each item opens the chat prefilled with a contextual intent
          // (never auto-sent). The intent text IS the accessible name — it
          // states exactly what the click does.
          const sender = mail.sender_name || mail.sender_email || '—';
          const intent = t('dashboard.briefing.intents.mail', {
            subject: mail.subject,
            sender,
          });
          const summarizeIntent = t('dashboard.briefing.intents_exec.mail_summarize', {
            subject: mail.subject,
            sender,
          });
          const replyIntent = t('dashboard.briefing.intents_exec.mail_reply', {
            subject: mail.subject,
            sender,
          });
          return (
            // QW-24: the action chips are SIBLINGS of the main button — a
            // button inside a button is invalid HTML and unreachable by AT.
            <li key={index} className="flex items-start gap-1">
              <button
                type="button"
                onClick={() => onOpenChat(intent)}
                aria-label={intent}
                className="min-w-0 flex-1 text-left flex flex-col gap-0.5 leading-tight rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 tabular-nums">
                  {mail.received_local}
                </span>
                <span className="text-sm font-medium text-foreground/90 truncate">
                  {mail.subject}
                </span>
                <span className="text-xs text-muted-foreground truncate">
                  {mail.sender_email || mail.sender_name || '—'}
                </span>
              </button>
              <CardItemActions
                actions={[
                  {
                    icon: Sparkles,
                    label: summarizeIntent,
                    onSelect: () => onExecute(summarizeIntent),
                  },
                  { icon: Reply, label: replyIntent, onSelect: () => onExecute(replyIntent) },
                ]}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
