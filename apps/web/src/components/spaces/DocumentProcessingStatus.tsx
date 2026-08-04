'use client';

import { useTranslation } from 'react-i18next';
import { CheckCircle, XCircle, Loader2, RefreshCw, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { RAGDocumentStatus } from '@/types/rag-spaces';
import { lifecycleTone } from '@/lib/status-tone';

interface DocumentProcessingStatusProps {
  status: RAGDocumentStatus;
  errorMessage?: string | null;
}

export function DocumentProcessingStatus({ status, errorMessage }: DocumentProcessingStatusProps) {
  const { t } = useTranslation();

  switch (status) {
    case 'pending':
      return (
        <Badge variant={lifecycleTone('pending')} className="gap-1.5">
          <Clock className="h-3 w-3" />
          {t('spaces.documents.status.pending')}
        </Badge>
      );

    case 'processing':
      return (
        <Badge variant={lifecycleTone('processing')} className="gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin" />
          {t('spaces.documents.status.processing')}
        </Badge>
      );

    case 'ready':
      return (
        <Badge variant={lifecycleTone('ready')} icon={<CheckCircle className="h-3 w-3" />}>
          {t('spaces.documents.status.ready')}
        </Badge>
      );

    case 'error':
      return (
        <Badge
          variant={lifecycleTone('error')}
          icon={<XCircle className="h-3 w-3" />}
          title={errorMessage || undefined}
        >
          {t('spaces.documents.status.error')}
        </Badge>
      );

    case 'reindexing':
      return (
        <Badge variant={lifecycleTone('reindexing')} className="gap-1.5">
          <RefreshCw className="h-3 w-3 animate-spin" />
          {t('spaces.documents.status.reindexing')}
        </Badge>
      );

    default:
      return null;
  }
}
