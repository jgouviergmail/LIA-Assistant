/**
 * The « + » offers the person's own documents — every knowledge space, active or not.
 *
 * The chat's search reads the ACTIVE spaces alone, so a document of a paused
 * space was unreachable from a question. This dialog lists the `ready`
 * documents of every space the person owns (a paused space is named and
 * badged, never hidden), searches them by name, bounds the selection by the
 * room left in the message, and turns each pick into an attachment through
 * the copy endpoint — a COPY for this turn, the space untouched.
 */

'use client';

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Loader2, Library } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchInput } from '@/components/ui/search-input';
import { useAttachableDocuments } from '@/hooks/useAttachableDocuments';
import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import apiClient from '@/lib/api-client';
import { getApiErrorCode } from '@/lib/api-error';
import { formatFileSize } from '@/lib/format';
import type { AttachableDocument } from '@/types/rag-spaces';

/** What the copy endpoint answers (the attachment row, as an upload's). */
interface AttachmentCreated {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  content_type: 'image' | 'document';
}

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

export function KnowledgeDocumentPickerDialog({
  open,
  onOpenChange,
  remaining,
  onAttached,
}: KnowledgeDocumentPickerDialogProps) {
  const { t } = useTranslation();
  const [needle, setNeedle] = useState('');
  const [selected, setSelected] = useState<AttachableDocument[]>([]);
  const [attaching, setAttaching] = useState(false);
  const { items, total, loading, error } = useAttachableDocuments(needle, open);

  const isSelected = (doc: AttachableDocument) => selected.some(s => s.id === doc.id);
  const full = selected.length >= remaining;

  const toggle = (doc: AttachableDocument) => {
    setSelected(prev =>
      prev.some(s => s.id === doc.id) ? prev.filter(s => s.id !== doc.id) : [...prev, doc]
    );
  };

  const close = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) {
        setSelected([]);
        setNeedle('');
      }
      onOpenChange(isOpen);
    },
    [onOpenChange]
  );

  const attach = async () => {
    setAttaching(true);
    let attached = 0;
    for (const doc of selected) {
      try {
        const created = await apiClient.post<AttachmentCreated>(
          '/attachments/from-knowledge-document',
          { space_id: doc.space_id, document_id: doc.id }
        );
        const outcome = onAttached({
          id: created.id,
          filename: doc.original_filename,
          mimeType: created.mime_type,
          size: created.file_size,
          contentType: created.content_type,
        });
        if ('error' in outcome) {
          toast.error(
            outcome.error === 'max_attachments'
              ? t('chat.attachments.max_attachments', { max: outcome.max })
              : t('chat.knowledge_picker.already_attached')
          );
          break;
        }
        attached += 1;
      } catch (err) {
        const code = getApiErrorCode(err);
        const key = code ? REFUSAL_KEYS[code] : undefined;
        toast.error(
          t(key ?? 'chat.knowledge_picker.attach_error', { name: doc.original_filename })
        );
      }
    }
    setAttaching(false);
    if (attached > 0) close(false);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Library className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('chat.knowledge_picker.title')}
          </DialogTitle>
          <DialogDescription>{t('chat.knowledge_picker.description')}</DialogDescription>
        </DialogHeader>

        <SearchInput
          placeholder={t('chat.knowledge_picker.search_placeholder')}
          aria-label={t('chat.knowledge_picker.search_placeholder')}
          onSearchChange={setNeedle}
          loading={loading}
        />

        <div className="min-h-[200px] max-h-[320px] overflow-y-auto rounded-md border">
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
              <span className="sr-only">{t('chat.knowledge_picker.loading')}</span>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-12 text-sm text-destructive">
              <p>{t('chat.knowledge_picker.error')}</p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-sm text-muted-foreground">
              <FileText className="h-8 w-8 mb-2" aria-hidden="true" />
              <p>
                {t(needle ? 'chat.knowledge_picker.empty_search' : 'chat.knowledge_picker.empty')}
              </p>
            </div>
          ) : (
            <ul className="divide-y">
              {items.map(doc => {
                const checked = isSelected(doc);
                const inputId = `knowledge-doc-${doc.id}`;
                return (
                  <li key={doc.id}>
                    <label
                      htmlFor={inputId}
                      className="flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent/50 transition-colors cursor-pointer"
                    >
                      <Checkbox
                        id={inputId}
                        checked={checked}
                        disabled={!checked && (full || attaching)}
                        onChange={() => toggle(doc)}
                      />
                      <FileText className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{doc.original_filename}</span>
                        <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          <span className="truncate">{doc.space_name}</span>
                          {!doc.space_is_active && (
                            <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal">
                              {t('chat.knowledge_picker.inactive_badge')}
                            </Badge>
                          )}
                          <span aria-hidden="true">·</span>
                          <span>{formatFileSize(doc.file_size)}</span>
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {total > items.length && (
          <p className="text-xs text-muted-foreground">
            {t('chat.knowledge_picker.more_hint', { shown: items.length, total })}
          </p>
        )}
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {t('chat.knowledge_picker.remaining', { count: remaining - selected.length })}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={attaching}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void attach()} disabled={selected.length === 0 || attaching}>
            {attaching && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('chat.knowledge_picker.attach', { count: selected.length })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
