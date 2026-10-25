/**
 * The « + » offers the person's own documents — every knowledge space, active or not.
 *
 * The chat's search reads the ACTIVE spaces alone, so a document of a paused
 * space was unreachable from a question. This picker lists the `ready`
 * documents of every space the person owns (a paused space is named and
 * badged, never hidden) and turns each pick into an attachment through the
 * copy endpoint — a COPY for this turn, the space untouched. The dialog is the
 * pickers' own (`AttachSourcePickerDialog`).
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Library } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { AttachSourcePickerDialog, type PickerWords } from './AttachSourcePickerDialog';
import { useAttachableDocuments } from '@/hooks/useAttachableDocuments';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import apiClient from '@/lib/api-client';
import type { AttachmentCreated } from '@/lib/attach-sources';
import { formatFileSize } from '@/lib/format';
import type { AttachableDocument } from '@/types/rag-spaces';

const WORDS: PickerWords = {
  title: 'chat.knowledge_picker.title',
  description: 'chat.knowledge_picker.description',
  searchPlaceholder: 'chat.knowledge_picker.search_placeholder',
  loading: 'chat.knowledge_picker.loading',
  empty: 'chat.knowledge_picker.empty',
  emptySearch: 'chat.knowledge_picker.empty_search',
  error: 'chat.knowledge_picker.error',
  moreHint: 'chat.knowledge_picker.more_hint',
  remaining: 'chat.knowledge_picker.remaining',
  attach: 'chat.knowledge_picker.attach',
  alreadyAttached: 'chat.knowledge_picker.already_attached',
  attachError: 'chat.knowledge_picker.attach_error',
};

/** The refusals the copy endpoint names, in the reader's words. */
const REFUSAL_KEYS: Record<string, string> = {
  document_not_ready: 'chat.knowledge_picker.not_ready',
};

interface KnowledgeDocumentPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Attachments the message can still take (the per-message cap minus the strip). */
  remaining: number;
  /** Hand a created attachment to the composer's strip. */
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome;
}

function DocumentMeta({ doc }: { doc: AttachableDocument }) {
  const { t } = useTranslation();
  return (
    <>
      <span className="truncate">{doc.space_name}</span>
      {!doc.space_is_active && (
        <Badge variant="outline" className="h-4 px-1 text-px-10 font-normal">
          {t('chat.knowledge_picker.inactive_badge')}
        </Badge>
      )}
      <span aria-hidden="true">·</span>
      <span>{formatFileSize(doc.file_size)}</span>
    </>
  );
}

export function KnowledgeDocumentPickerDialog(props: KnowledgeDocumentPickerDialogProps) {
  const [needle, setNeedle] = useState('');
  const page = useAttachableDocuments(needle, props.open);
  return (
    <AttachSourcePickerDialog<AttachableDocument>
      {...props}
      icon={Library}
      itemIcon={FileText}
      words={WORDS}
      needle={needle}
      onNeedleChange={setNeedle}
      page={page}
      idOf={doc => doc.id}
      labelOf={doc => doc.original_filename}
      nameOf={doc => doc.original_filename}
      metaOf={doc => <DocumentMeta doc={doc} />}
      copy={doc =>
        apiClient.post<AttachmentCreated>('/attachments/from-knowledge-document', {
          space_id: doc.space_id,
          document_id: doc.id,
        })
      }
      refusals={REFUSAL_KEYS}
    />
  );
}
