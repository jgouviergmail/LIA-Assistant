'use client';

/**
 * The documents of a space with their selection (ADR-259): the rows, the bar
 * once something is selected, the move dialog, the confirmed bulk delete,
 * and the toasts that state what moved, what was deleted and what was left
 * in place — with the reasons, never a silent partial success.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { DocumentRow } from '@/components/spaces/DocumentRow';
import { DocumentSelectionBar } from '@/components/spaces/DocumentSelectionBar';
import { MoveDocumentsDialog } from '@/components/spaces/MoveDocumentsDialog';
import { useConfirm } from '@/components/ui/use-confirm';
import { skippedSentence } from '@/lib/batch-report';
import { pageSelectionState, toggleId } from '@/lib/selection';
import type { RAGDocument, RAGDocumentBatchResponse, RAGSpace } from '@/types/rag-spaces';

export interface DocumentsSectionProps {
  documents: RAGDocument[];
  /** The spaces a document may move to (the current one excluded). */
  otherSpaces: RAGSpace[];
  deleting: boolean;
  moving: boolean;
  bulkDeleting: boolean;
  downloadHref: (documentId: string) => string;
  archiveHref: (documentIds: string[]) => string;
  onDeleteDocument: (documentId: string) => Promise<void>;
  moveDocuments: (ids: string[], targetSpaceId: string) => Promise<RAGDocumentBatchResponse | null>;
  bulkDeleteDocuments: (ids: string[]) => Promise<RAGDocumentBatchResponse | null>;
}

export function DocumentsSection({
  documents,
  otherSpaces,
  deleting,
  moving,
  bulkDeleting,
  downloadHref,
  archiveHref,
  onDeleteDocument,
  moveDocuments,
  bulkDeleteDocuments,
}: DocumentsSectionProps) {
  const { t } = useTranslation();
  const { confirm, confirmDialog } = useConfirm();
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const [moveIds, setMoveIds] = useState<string[] | null>(null);

  const ids = documents.map(doc => doc.id);
  const chosen = ids.filter(id => selected.has(id));
  const pageState = pageSelectionState(ids, selected);

  const submitMove = async (target: string) => {
    if (moveIds === null || moving) return;
    const result = await moveDocuments(moveIds, target);
    setMoveIds(null);
    if (result === null) {
      toast.error(t('common.error'));
      return;
    }
    if (result.done.length > 0) {
      toast.success(t('spaces.documents.moved', { count: result.done.length }));
    }
    if (result.skipped.length > 0) {
      toast.info(skippedSentence(t, 'spaces.documents', result.skipped));
    }
    setSelected(new Set());
  };

  const removeSelected = async () => {
    if (chosen.length === 0 || bulkDeleting) return;
    const ok = await confirm({
      title: t('spaces.documents.confirm_bulk_delete_title'),
      description: t('spaces.documents.confirm_bulk_delete_description', { count: chosen.length }),
      confirmLabel: t('spaces.documents.delete_selected'),
      destructive: true,
    });
    if (!ok) return;
    const result = await bulkDeleteDocuments(chosen);
    if (result === null) {
      toast.error(t('spaces.documents.delete_error'));
      return;
    }
    if (result.done.length > 0) {
      toast.success(t('spaces.documents.bulk_deleted', { count: result.done.length }));
    }
    if (result.skipped.length > 0) {
      toast.info(skippedSentence(t, 'spaces.documents', result.skipped));
    }
    setSelected(new Set());
  };

  return (
    <div className="space-y-3">
      {confirmDialog}
      {chosen.length > 0 && (
        <DocumentSelectionBar
          count={chosen.length}
          pageState={pageState}
          archiveHref={archiveHref(chosen)}
          onSelectAll={() => setSelected(new Set(ids))}
          onClear={() => setSelected(new Set())}
          onMove={() => setMoveIds(chosen)}
          onDelete={() => void removeSelected()}
          deleting={bulkDeleting}
        />
      )}
      <ul className="space-y-2">
        {documents.map(doc => (
          <DocumentRow
            key={doc.id}
            document={doc}
            selected={selected.has(doc.id)}
            onToggle={() => setSelected(toggleId(selected, doc.id))}
            onDelete={id => void onDeleteDocument(id)}
            onMove={id => setMoveIds([id])}
            downloadHref={downloadHref(doc.id)}
            deleting={deleting}
          />
        ))}
      </ul>
      <MoveDocumentsDialog
        open={moveIds !== null}
        onOpenChange={open => !open && setMoveIds(null)}
        spaces={otherSpaces}
        count={moveIds?.length ?? 0}
        isMoving={moving}
        onSubmit={target => void submitMove(target)}
      />
    </div>
  );
}
