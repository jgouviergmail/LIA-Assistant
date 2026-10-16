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

function documentTypeKey(mime: string | null): string {
  if (mime === 'application/pdf') return 'type_pdf';
  if (mime?.includes('spreadsheet') || mime === 'application/vnd.ms-excel') {
    return 'type_spreadsheet';
  }
  if (
    mime?.startsWith('text/') ||
    mime?.includes('wordprocessingml') ||
    mime === 'application/msword' ||
    mime === 'application/vnd.google-apps.document'
  ) {
    return 'type_text';
  }
  return 'type_file';
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
            contentClassName="flex flex-col gap-1.5 leading-snug"
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
            <span className="flex items-center gap-1.5 text-xs font-medium text-indigo-700 dark:text-indigo-300 tabular-nums">
              <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {doc.modified_local}
            </span>
            <span className="line-clamp-2 break-words text-sm font-semibold text-foreground/90">
              {doc.name}
            </span>
            <span className="text-xs text-muted-foreground">
              {t(`dashboard.briefing.cards.documents.${documentTypeKey(doc.mime_type)}`)}
            </span>
          </CardItemRow>
        );
      })}
    </ul>
  );
}
