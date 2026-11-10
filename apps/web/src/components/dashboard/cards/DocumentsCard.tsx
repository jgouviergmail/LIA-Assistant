'use client';

import {
  Download,
  ExternalLink,
  FileText,
  MessageCircleQuestion,
  Send,
  Sparkles,
} from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { BriefingCard } from '../BriefingCard';
import type { CardItemAction } from './CardItemActions';
import { CardItemRow } from './CardItemRow';
import { useHomeTools, type HomeTools } from '../HomeTools';
import { chatDraftHref, chatIntentHref } from '@/lib/chat-href';
import { documentHref, homeLanguage } from '@/lib/briefing-tools';
import { driveName } from '@/lib/drives';
import { downloadUrl } from '@/lib/workbench/files';
import { driveAttachment } from '@/lib/workbench/mail-compose';
import { useDashboardChat } from '../DashboardNavigation';
import type { Language } from '@/i18n/settings';
import type { CardSection, DocumentItem, DocumentsData } from '@/types/briefing';

interface DocumentsCardProps {
  section: CardSection<DocumentsData>;
  isRefreshing: boolean;
  onRefresh: () => void;
  staggerIndex?: number;
}

/**
 * Documents card (P15 extension, 2026-07-22).
 *
 * Latest modified files of the connected drive, Google Drive or OneDrive. Where
 * the instance offers the « Tools », a file opens in the files tool, downloads
 * through it, and leaves in a new message of the mail tool (owner, 2026-11-07);
 * else the row opens the chat prefilled with a summarize intent (QW-9 `?draft=`).
 * The file on its drive stays one anchor away (user arbitration: both).
 */
export function DocumentsCard({
  section,
  isRefreshing,
  onRefresh,
  staggerIndex,
}: DocumentsCardProps) {
  const { i18n } = useTranslation();
  const openChat = useDashboardChat();
  const lng = homeLanguage(i18n.language);
  const tools = useHomeTools();
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
          lng={lng}
          tools={tools}
          onOpenChat={draft => openChat(chatDraftHref(lng, draft))}
          onExecute={intent => openChat(chatIntentHref(lng, intent))}
        />
      )}
      staggerIndex={staggerIndex}
    />
  );
}

/** Where a file lives: its drive, then its folders; nothing when that is unknown. */
function place(provider: string | null, path: string | null | undefined): string | null {
  if (provider === null || path === null || path === undefined) return null;
  return [driveName(provider), ...path.split('/').filter(Boolean)].join(' / ');
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
  lng,
  tools,
  onOpenChat,
  onExecute,
}: {
  data: DocumentsData;
  lng: Language;
  tools: HomeTools;
  onOpenChat: (draft: string) => void;
  onExecute: (intent: string) => void;
}) {
  const { t } = useTranslation();
  /** Direct first: the Tools' download and new message, then the file on its drive. */
  const directActs = (doc: DocumentItem): CardItemAction[] => {
    const id = doc.id;
    const tooled: CardItemAction[] =
      tools.offered && id
        ? [
            // The Tools' own download: a Google document leaves in its first export format.
            {
              icon: Download,
              label: t('dashboard.briefing.home_acts.download'),
              href: downloadUrl(id, null),
            },
            ...(tools.offers('compose')
              ? [
                  {
                    icon: Send,
                    label: t('dashboard.briefing.home_acts.send_by_mail'),
                    onSelect: () =>
                      tools.go({
                        kind: 'compose',
                        to: '',
                        file: driveAttachment({
                          id,
                          name: doc.name,
                          mime_type: doc.mime_type ?? 'application/octet-stream',
                        }),
                      }),
                  },
                ]
              : []),
          ]
        : [];
    // Opening the file in Drive is a real anchor (`href`): navigation deserves the
    // browser's own affordances — middle-click, context menu, status-bar preview.
    const drive: CardItemAction[] = doc.web_view_link
      ? [
          {
            icon: ExternalLink,
            label: t('dashboard.briefing.cards.documents.open_external', { subject: doc.name }),
            href: doc.web_view_link,
          },
        ]
      : [];
    return [...tooled, ...drive];
  };
  return (
    <ul className="space-y-0.5" role="list">
      {data.items.map((doc, index) => {
        const intent = t('dashboard.briefing.intents.document_summarize', {
          subject: doc.name,
        });
        const href = tools.offered ? documentHref(doc, lng) : null;
        const target = href
          ? { href, ariaLabel: t('dashboard.briefing.open_in.document', { subject: doc.name }) }
          : { onSelect: () => onOpenChat(intent), ariaLabel: intent };
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
            key={doc.id ?? index}
            {...target}
            tooltip={doc.name}
            contentClassName="flex flex-col gap-1.5 leading-snug"
            actions={[
              ...directActs(doc),
              {
                icon: Sparkles,
                label: summarizeIntent,
                opensChat: true,
                onSelect: () => onExecute(summarizeIntent),
              },
              {
                icon: MessageCircleQuestion,
                label: t('dashboard.briefing.intents_exec.document_ask_label', {
                  subject: doc.name,
                }),
                onSelect: () => onOpenChat(askDraft),
              },
            ]}
          >
            <span className="flex items-center gap-1.5 text-xs font-medium text-indigo-700 dark:text-indigo-300 tabular-nums">
              <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {doc.modified_local}
            </span>
            <span className="line-clamp-2 break-words text-sm font-semibold text-foreground/90">
              {doc.name}
            </span>
            {place(data.provider, doc.path) && (
              <span className="truncate text-xs text-muted-foreground">
                {place(data.provider, doc.path)}
              </span>
            )}
            <span className="text-xs text-muted-foreground">
              {t(`dashboard.briefing.cards.documents.${documentTypeKey(doc.mime_type)}`)}
            </span>
          </CardItemRow>
        );
      })}
    </ul>
  );
}
