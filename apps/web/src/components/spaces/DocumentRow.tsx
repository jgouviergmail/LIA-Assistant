'use client';

import { useTranslation } from 'react-i18next';
import { Coins, FileText, FileType2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DocumentProcessingStatus } from './DocumentProcessingStatus';
import { formatFileSize } from '@/lib/format';
import type { RAGDocument } from '@/types/rag-spaces';

interface DocumentRowProps {
  document: RAGDocument;
  onDelete: (documentId: string) => void;
  deleting?: boolean;
}

function getFileIcon(contentType: string) {
  if (contentType === 'application/pdf') {
    return <FileType2 className="h-4 w-4 text-muted-foreground" />;
  }
  return <FileText className="h-4 w-4 text-muted-foreground" />;
}

export function DocumentRow({ document: doc, onDelete, deleting }: DocumentRowProps) {
  const { t } = useTranslation();

  return (
    <div className="group flex items-center gap-3 rounded-lg border p-3 bg-card hover:bg-accent/50 transition-colors">
      {/* File icon */}
      <div className="shrink-0 rounded-lg bg-muted p-2">
        {getFileIcon(doc.content_type)}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{doc.original_filename}</p>
        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
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
                <Coins className="h-3 w-3" />
                {t('spaces.documents.embedding_tokens', { count: doc.embedding_tokens.toLocaleString() } as Record<string, string>)}
                {doc.embedding_cost_eur > 0 && (
                  <span>({doc.embedding_cost_eur.toFixed(6)} €)</span>
                )}
              </span>
            </>
          )}
          <span>·</span>
          <span>{new Date(doc.created_at).toLocaleDateString()}</span>
        </div>
      </div>

      {/* Status */}
      <DocumentProcessingStatus status={doc.status} errorMessage={doc.error_message} />

      {/* Delete */}
      <Button
        variant="ghost"
        size="icon"
        className="shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"
        onClick={() => onDelete(doc.id)}
        disabled={deleting}
        title={t('common.delete')}
      >
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  );
}
