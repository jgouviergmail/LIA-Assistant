'use client';

/**
 * One document of a knowledge space (ADR-259): a named checkbox for the
 * selection, the file's facts, its indexing state, and its actions ONE way
 * (ADR-208, `RowActions`) — download as a real link, move (uploads only:
 * Drive keeps its own files in sync and a meeting owns its minutes), delete
 * red at rest. Nothing is revealed by hover.
 */

import {
  ClipboardList,
  Coins,
  FileText,
  FileType2,
  FolderInput,
  HardDriveDownload,
  Trash2,
} from 'lucide-react';
import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { formatFileSize } from '@/lib/format';
import type { RAGDocument } from '@/types/rag-spaces';

import { DocumentProcessingStatus } from './DocumentProcessingStatus';

export interface DocumentRowProps {
  document: RAGDocument;
  selected: boolean;
  onToggle: () => void;
  onDelete: (documentId: string) => void;
  onMove: (documentId: string) => void;
  /** The download endpoint of this document's file. */
  downloadHref: string;
  deleting?: boolean;
}

function getFileIcon(contentType: string) {
  if (contentType === 'application/pdf') {
    return <FileType2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />;
  }
  return <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />;
}

/** Only an upload may move: the other sources are owned by another system. */
export function isMovable(document: Pick<RAGDocument, 'source_type'>): boolean {
  return document.source_type === 'upload';
}

function SourceBadge({ document: doc }: { document: RAGDocument }) {
  const { t } = useTranslation();
  if (doc.source_type === 'drive') {
    return (
      <Badge variant="outline" size="sm" icon={<HardDriveDownload className="h-2.5 w-2.5" />}>
        {t('spaces.drive.source_type_drive')}
      </Badge>
    );
  }
  if (doc.source_type === 'meeting') {
    return (
      <Badge variant="outline" size="sm" icon={<ClipboardList className="h-2.5 w-2.5" />}>
        {t('spaces.meetings.source_type_meeting')}
      </Badge>
    );
  }
  return null;
}

function Facts({ document: doc }: { document: RAGDocument }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span>{formatFileSize(doc.file_size)}</span>
      {doc.status === 'ready' && (
        <>
          <span>·</span>
          <span>{t('spaces.documents.chunk_count', { count: doc.chunk_count })}</span>
        </>
      )}
      {doc.status === 'ready' && doc.embedding_tokens > 0 && (
        <>
          <span>·</span>
          <span className="inline-flex items-center gap-1">
            <Coins className="h-3 w-3" aria-hidden="true" />
            {t('spaces.documents.embedding_tokens', {
              count: doc.embedding_tokens.toLocaleString(),
            } as Record<string, string>)}
            {doc.embedding_cost_eur > 0 && <span>({doc.embedding_cost_eur.toFixed(6)} €)</span>}
          </span>
        </>
      )}
      <span>·</span>
      <span>{new Date(doc.created_at).toLocaleDateString()}</span>
    </div>
  );
}

export function DocumentRow({
  document: doc,
  selected,
  onToggle,
  onDelete,
  onMove,
  downloadHref,
  deleting,
}: DocumentRowProps) {
  const { t } = useTranslation();
  const name = doc.original_filename;
  const actions: RowAction[] = [
    {
      key: 'download',
      label: t('spaces.documents.download'),
      icon: Download,
      href: downloadHref,
      onSelect: () => undefined,
    },
  ];
  if (isMovable(doc)) {
    actions.push({
      key: 'move',
      label: t('spaces.documents.move'),
      icon: FolderInput,
      onSelect: () => onMove(doc.id),
    });
  }
  actions.push({
    key: 'delete',
    label: t('common.delete'),
    icon: Trash2,
    tone: 'destructive',
    onSelect: () => onDelete(doc.id),
    loading: deleting,
  });

  return (
    <li
      aria-label={name}
      className="flex items-center gap-2 rounded-lg border bg-card p-2 pr-3 transition-colors sm:gap-3"
    >
      {/* 44 px touch target around the native 16 px box: the label is part of
          the target, and its (visually hidden) text is the checkbox's name. */}
      <label className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center">
        <Checkbox checked={selected} onChange={onToggle} />
        <span className="sr-only">{t('spaces.documents.select_row', { name })}</span>
      </label>
      <div className="shrink-0 rounded-lg bg-muted p-2">{getFileIcon(doc.content_type)}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-sm font-medium">{name}</p>
          <SourceBadge document={doc} />
        </div>
        <Facts document={doc} />
      </div>
      <DocumentProcessingStatus status={doc.status} errorMessage={doc.error_message} />
      <RowActions actions={actions} menuLabel={t('spaces.documents.row_actions', { name })} />
    </li>
  );
}
