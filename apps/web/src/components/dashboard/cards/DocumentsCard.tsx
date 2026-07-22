'use client';

import { ExternalLink, FileText } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import { chatDraftHref } from '@/lib/briefing-utils';
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
  const router = useRouter();
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
          onOpenChat={draft => router.push(chatDraftHref(lng, draft))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

function DocumentsContent({
  data,
  onOpenChat,
}: {
  data: DocumentsData;
  onOpenChat: (draft: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-0.5" role="list">
      {data.items.map((doc, index) => {
        const intent = t('dashboard.briefing.intents.document_summarize', {
          subject: doc.name,
        });
        return (
          <li key={index} className="flex items-baseline gap-1.5">
            <button
              type="button"
              onClick={() => onOpenChat(intent)}
              aria-label={intent}
              className="min-w-0 flex-1 text-left flex items-baseline justify-between gap-2 text-sm rounded-md px-1.5 py-1 -mx-1.5 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="truncate font-medium text-foreground/90">{doc.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {doc.modified_local}
              </span>
            </button>
            {doc.web_view_link && (
              <a
                href={doc.web_view_link}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t('dashboard.briefing.cards.documents.open_external', {
                  subject: doc.name,
                })}
                className="shrink-0 p-1 rounded-md text-muted-foreground hover:text-indigo-600 dark:hover:text-indigo-300 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
