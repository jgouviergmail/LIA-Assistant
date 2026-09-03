/**
 * One linked Gmail label (ADR-262) — the shared source card, mail wording.
 *
 * Phase: evolution — RAG Spaces (Gmail label source)
 */

'use client';

import { useTranslation } from 'react-i18next';
import { Mail } from 'lucide-react';

import { SourceSyncCard } from '@/components/spaces/SourceSyncCard';
import type { RAGMailSource, RAGSourceSyncStatus } from '@/types/rag-spaces';

interface MailSourceCardProps {
  source: RAGMailSource;
  onSync: (sourceId: string) => void;
  onUnlink: (sourceId: string) => void;
  syncing?: boolean;
}

const STATUS_KEYS: Record<RAGSourceSyncStatus, string> = {
  idle: 'spaces.mail.status_idle',
  syncing: 'spaces.mail.status_syncing',
  completed: 'spaces.mail.status_completed',
  error: 'spaces.mail.status_error',
};

export function MailSourceCard({ source, onSync, onUnlink, syncing }: MailSourceCardProps) {
  const { t } = useTranslation();

  return (
    <SourceSyncCard
      icon={<Mail className="h-4 w-4 text-primary" />}
      title={source.label_name}
      status={source.sync_status}
      statusKeys={STATUS_KEYS}
      syncedLabel={t('spaces.mail.synced_count', { count: source.synced_thread_count })}
      totalLabel={t('spaces.mail.threads_count', { count: source.thread_count })}
      lastSyncAt={source.last_sync_at}
      lastSyncedLabel={time => t('spaces.mail.last_synced', { time })}
      errorMessage={source.error_message}
      onSync={() => onSync(source.id)}
      onUnlink={() => onUnlink(source.id)}
      syncing={syncing}
      syncTitle={t('spaces.mail.sync_now')}
      unlinkTitle={t('spaces.mail.unlink')}
    />
  );
}
