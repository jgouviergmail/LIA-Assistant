'use client';

import { Archive, Eye, Mail, MailOpen, Reply, Sparkles } from '@/lib/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import type { CardItemAction } from './CardItemActions';
import { CardItemRow } from './CardItemRow';
import { homeActs, useHomeAct } from './useHomeActs';
import { useHomeTools, type HomeTools } from '../HomeTools';
import { chatDraftHref, chatIntentHref } from '@/lib/chat-href';
import { homeLanguage, mailHref } from '@/lib/briefing-tools';
import { useDashboardChat, useDashboardRoute } from '../DashboardNavigation';
import { canWatch } from '@/lib/mail-watch';
import { useMailWatch } from '@/hooks/useMailWatch';
import { ClassificationBadges } from '@/components/chat/ClassificationBadges';
import type { Language } from '@/i18n/settings';
import type { CardSection, MailItem, MailsData } from '@/types/briefing';

interface MailsCardProps {
  section: CardSection<MailsData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  /** Reload after a direct act, independently of manual refresh feedback. */
  onInvalidate?: () => void;
  staggerIndex?: number;
}

/**
 * Unread mail of the day. Where the instance offers the « Tools », a message opens in the mail
 * tool, and it is marked read or archived there in one press — the Tools' own routes, the card
 * read again after (owner, 2026-11-07); LIA's acts keep the chat.
 */
export function MailsCard({
  section,
  isRefreshing,
  onRefresh,
  onInvalidate,
  staggerIndex,
}: MailsCardProps) {
  const router = useRouter();
  const navigate = useDashboardRoute(router.push);
  const { i18n } = useTranslation();
  const openChat = useDashboardChat();
  const lng = homeLanguage(i18n.language);
  const tools = useHomeTools();
  return (
    <BriefingCard<MailsData>
      titleKey="dashboard.briefing.cards.mails.title"
      icon={<Mail className="h-5 w-5" />}
      tone="emerald"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.mails.empty"
      onErrorCta={() => navigate(`/${lng}/dashboard/settings?section=connectors`)}
      renderContent={data => (
        <MailsContent
          data={data}
          lng={lng}
          tools={tools}
          onOpenChat={draft => openChat(chatDraftHref(lng, draft))}
          onExecute={intent => openChat(chatIntentHref(lng, intent))}
          onActed={onInvalidate ?? onRefresh}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function MailsContent({
  data,
  lng,
  tools,
  onOpenChat,
  onExecute,
  onActed,
}: {
  data: MailsData;
  lng: Language;
  tools: HomeTools;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
  onActed: () => void;
}) {
  const { t } = useTranslation();
  // A watch is a CONDITION routine the chat cannot author (ADR-281, lot 5):
  // `create_scheduled_action_tool` creates `time` routines only, by a written
  // decision, so this chip writes rather than opening a prefilled conversation.
  const { watch, loading: watching } = useMailWatch();
  const { busy, run, list } = useHomeAct(onActed);

  /** The acts that need no model: the Tools' routes, then the watch. */
  const directActs = (mail: MailItem, sender: string): CardItemAction[] => {
    const id = mail.id;
    const tooled: CardItemAction[] =
      tools.offered && id
        ? [
            {
              icon: MailOpen,
              label: t('dashboard.briefing.home_acts.mark_read'),
              busy: busy === id,
              onSelect: () =>
                void run(id, () => homeActs.markRead(id), 'dashboard.briefing.home_acts_done.read'),
            },
            {
              icon: Archive,
              label: t('dashboard.briefing.home_acts.archive'),
              busy: busy === id,
              onSelect: () =>
                void run(
                  id,
                  () => homeActs.archive(id),
                  'dashboard.briefing.home_acts_done.archived'
                ),
            },
          ]
        : [];
    // Offered only when a sender came through: a mail with neither an address
    // nor a name gives nothing to watch FOR.
    const watchAct: CardItemAction[] = canWatch(mail)
      ? [
          {
            icon: Eye,
            label: t('dashboard.briefing.watch.action', { sender }),
            onSelect: () => {
              if (!watching) void watch(mail, sender);
            },
          },
        ]
      : [];
    return [...tooled, ...watchAct];
  };

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
      <ul ref={list} className="space-y-1.5" role="list">
        {data.items.map((mail, index) => {
          const sender = mail.sender_name || mail.sender_email || '—';
          // Where the Tools are offered the row opens the message in its tool; else (QW-9) the
          // chat, prefilled, never sent. The row's name says what the click does.
          const intent = t('dashboard.briefing.intents.mail', { subject: mail.subject, sender });
          const href = tools.offered ? mailHref(mail, lng) : null;
          const target = href
            ? {
                href,
                ariaLabel: t('dashboard.briefing.open_in.mail', { subject: mail.subject, sender }),
              }
            : { onSelect: () => onOpenChat(intent), ariaLabel: intent };
          const summarizeIntent = t('dashboard.briefing.intents_exec.mail_summarize', {
            subject: mail.subject,
            sender,
          });
          const replyIntent = t('dashboard.briefing.intents_exec.mail_reply', {
            subject: mail.subject,
            sender,
          });
          const from =
            mail.sender_name && mail.sender_email
              ? `${mail.sender_name} · ${mail.sender_email}`
              : mail.sender_email || mail.sender_name || '—';
          return (
            <CardItemRow
              key={mail.id ?? index}
              {...target}
              // Subject AND sender: two truncated lines, and a subject alone
              // rarely says which conversation this is.
              tooltip={`${mail.subject}\n${from}`}
              contentClassName="flex flex-col gap-1.5 leading-snug"
              actions={[
                ...directActs(mail, sender),
                {
                  icon: Sparkles,
                  label: summarizeIntent,
                  opensChat: true,
                  onSelect: () => onExecute(summarizeIntent),
                },
                {
                  icon: Reply,
                  label: replyIntent,
                  opensChat: true,
                  onSelect: () => onExecute(replyIntent),
                },
              ]}
            >
              <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-300 tabular-nums">
                <Mail className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {mail.received_local}
              </span>
              <span className="line-clamp-2 break-words text-sm font-semibold text-foreground/90">
                {mail.subject}
              </span>
              <span className="line-clamp-2 break-words text-xs text-muted-foreground">{from}</span>
              <ClassificationBadges value={mail.classification} />
            </CardItemRow>
          );
        })}
      </ul>
    </div>
  );
}
