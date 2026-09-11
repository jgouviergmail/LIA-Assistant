'use client';

import { Eye, Mail, Reply, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemRow } from './CardItemRow';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import { canWatch } from '@/lib/mail-watch';
import { useMailWatch } from '@/hooks/useMailWatch';
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
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onExecute={intent => openChatDeepLink(chatIntentHref(lng, intent))}
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
  // A watch is a CONDITION routine the chat cannot author (ADR-281, lot 5):
  // `create_scheduled_action_tool` creates `time` routines only, by a written
  // decision, so this chip is the one gesture here that writes rather than
  // opening a prefilled conversation.
  const { watch, loading: watching } = useMailWatch();
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
          const from = mail.sender_email || mail.sender_name || '—';
          return (
            <CardItemRow
              key={index}
              ariaLabel={intent}
              // Subject AND sender: two truncated lines, and a subject alone
              // rarely says which conversation this is.
              tooltip={`${mail.subject}\n${from}`}
              onSelect={() => onOpenChat(intent)}
              contentClassName="flex flex-col gap-0.5 leading-tight"
              actions={[
                {
                  icon: Sparkles,
                  label: summarizeIntent,
                  onSelect: () => onExecute(summarizeIntent),
                },
                { icon: Reply, label: replyIntent, onSelect: () => onExecute(replyIntent) },
                // Offered only when a sender came through: a mail with neither
                // an address nor a name gives nothing to watch FOR, and a chip
                // whose only outcome is an error is worse than no chip.
                ...(canWatch(mail)
                  ? [
                      {
                        icon: Eye,
                        label: t('dashboard.briefing.watch.action', { sender }),
                        onSelect: () => {
                          if (!watching) void watch(mail, sender);
                        },
                      },
                    ]
                  : []),
              ]}
            >
              <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300 tabular-nums">
                {mail.received_local}
              </span>
              <span className="text-sm font-medium text-foreground/90 truncate">
                {mail.subject}
              </span>
              <span className="text-xs text-muted-foreground truncate">{from}</span>
            </CardItemRow>
          );
        })}
      </ul>
    </div>
  );
}
