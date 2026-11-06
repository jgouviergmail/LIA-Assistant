/**
 * Card displaying a folder linked from a drive with sync status and actions.
 *
 * A folder belongs to the drive it was linked on: while another one is connected
 * it waits, its documents kept, and says which drive it waits for.
 *
 * The card itself is shared with the Gmail label source (ADR-262):
 * `SourceSyncCard` owns the layout, the lifecycle tone and the two actions;
 * this file owns the Drive icon and wording.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useTranslation } from 'react-i18next';
import { FolderSync } from 'lucide-react';

import { SourceSyncCard } from '@/components/spaces/SourceSyncCard';
import { driveName } from '@/lib/drives';
import type { RAGDriveSource, RAGSourceSyncStatus } from '@/types/rag-spaces';

interface DriveSourceCardProps {
  source: RAGDriveSource;
  /** The drive the account has connected now. */
  activeDrive: string | null;
  onSync: (sourceId: string) => void;
  onUnlink: (sourceId: string) => void;
  syncing?: boolean;
}

const STATUS_KEYS: Record<RAGSourceSyncStatus, string> = {
  idle: 'spaces.drive.status_idle',
  syncing: 'spaces.drive.status_syncing',
  completed: 'spaces.drive.status_completed',
  error: 'spaces.drive.status_error',
};

export function DriveSourceCard({
  source,
  activeDrive,
  onSync,
  onUnlink,
  syncing,
}: DriveSourceCardProps) {
  const { t } = useTranslation();
  const paused = source.provider !== activeDrive;

  return (
    <SourceSyncCard
      icon={<FolderSync className="h-4 w-4 text-primary" />}
      title={source.folder_name}
      status={source.sync_status}
      statusKeys={STATUS_KEYS}
      syncedLabel={t('spaces.drive.synced_count', { count: source.synced_file_count })}
      totalLabel={t('spaces.drive.files_count', { count: source.file_count })}
      lastSyncAt={source.last_sync_at}
      lastSyncedLabel={time => t('spaces.drive.last_synced', { time })}
      errorMessage={source.error_message}
      pausedNote={
        paused
          ? t('spaces.drive.paused', { drive: driveName(source.provider) })
          : undefined
      }
      onSync={() => onSync(source.id)}
      onUnlink={() => onUnlink(source.id)}
      syncing={syncing}
      syncTitle={t('spaces.drive.sync_now')}
      unlinkTitle={t('spaces.drive.unlink')}
    />
  );
}
