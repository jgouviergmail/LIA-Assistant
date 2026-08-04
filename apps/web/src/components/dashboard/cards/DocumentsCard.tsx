'use client';

import { ExternalLink, FileText, MessageCircleQuestion, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { CardItemRow } from './CardItemRow';
import { chatDraftHref, chatIntentHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { CardSection, DocumentsData } from '@/types/briefing';

interface DocumentsCardProps {
  section: CardSection<DocumentsData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * Documents card (P15 extension, 2026-07-22 — Drive source arbitration).
 *
 * Latest modified Google Drive files. Each row is a button opening the chat
 * prefilled with a summarize intent (QW-9 `?draft=`), plus a separate
 * external-link anchor to the file in Drive (user arbitration: both).
 */
export function DocumentsCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: DocumentsCardProps) {
  const { i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  return (
    <BriefingCard<DocumentsData>
      titleKey="dashboard.briefing.cards.documents.title"
      icon={<FileText className="h-5 w-5" />}
      tone="indigo"
      section={section}
      isRefreshing={isRefreshing}
      onRefresh={onRefresh}
      emptyStateKey="dashboard.briefing.cards.documents.empty"
      renderContent={data => (
        <DocumentsContent
          data={data}
          onOpenChat={draft => openChatDeepLink(chatDraftHref(lng, draft))}
          onExecute={intent => openChatDeepLink(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function DocumentsContent({
  data,
  onOpenChat,
  onExecute,
}: {
  data: DocumentsData;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-0.5" role="list">
      {data.items.map((doc, index) => {
        const intent = t('dashboard.briefing.intents.document_summarize', {
          subject: doc.name,
        });
        const summarizeIntent = t('dashboard.briefing.intents_exec.document_summarize', {
          subject: doc.name,
        });
        // "Ask a question" needs the user's OWN words — it PREFILLS (draft
        // semantics) instead of executing; the two coexist by design.
        const askDraft = t('dashboard.briefing.intents_exec.document_ask_draft', {
          subject: doc.name,
        });
        return (
          <CardItemRow
            key={index}
            ariaLabel={intent}
            tooltip={doc.name}
            onSelect={() => onOpenChat(intent)}
            align="center"
            contentClassName="flex items-baseline justify-between gap-2 text-sm"
            actions={[
              {
                icon: Sparkles,
                label: summarizeIntent,
                onSelect: () => onExecute(summarizeIntent),
              },
              {
                icon: MessageCircleQuestion,
                label: t('dashboard.briefing.intents_exec.document_ask_label', {
                  subject: doc.name,
                }),
                onSelect: () => onOpenChat(askDraft),
              },
              // Opening the file in Drive joins the menu as a real anchor
              // (`href`) rather than sitting beside it as a fourth icon: it was
              // the widest row of the grid, and navigation deserves the
              // browser's own affordances — middle-click, context menu,
              // status-bar preview.
              ...(doc.web_view_link
                ? [
                    {
                      icon: ExternalLink,
                      label: t('dashboard.briefing.cards.documents.open_external', {
                        subject: doc.name,
                      }),
                      href: doc.web_view_link,
                    },
                  ]
                : []),
            ]}
          >
            <span className="truncate font-medium text-foreground/90">{doc.name}</span>
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
              {doc.modified_local}
            </span>
          </CardItemRow>
        );
      })}
    </ul>
  );
}
