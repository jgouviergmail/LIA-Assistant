/**
 * Card displaying a linked Google Drive folder source with sync status and actions.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useTranslation } from 'react-i18next';
import {
  FolderSync,
  RefreshCw,
  Unlink,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { RAGDriveSource, RAGDriveSyncStatus } from '@/types/rag-spaces';

interface DriveSourceCardProps {
  source: RAGDriveSource;
  onSync: (sourceId: string) => void;
  onUnlink: (sourceId: string) => void;
  syncing?: boolean;
}

/** Map sync status to badge variant and icon. */
function getSyncStatusDisplay(status: RAGDriveSyncStatus) {
  switch (status) {
    case 'syncing':
      return {
        variant: 'info' as const,
        icon: <Loader2 className="h-3 w-3 animate-spin" />,
        key: 'spaces.drive.status_syncing',
      };
    case 'completed':
      return {
        variant: 'success' as const,
        icon: <CheckCircle className="h-3 w-3" />,
        key: 'spaces.drive.status_completed',
      };
    case 'error':
      return {
        variant: 'destructive' as const,
        icon: <AlertCircle className="h-3 w-3" />,
        key: 'spaces.drive.status_error',
      };
    case 'idle':
    default:
      return {
        variant: 'outline' as const,
        icon: <Clock className="h-3 w-3" />,
        key: 'spaces.drive.status_idle',
      };
  }
}

/** Format a relative time string without date-fns. */
function formatRelativeTime(dateString: string): string {
  const now = Date.now();
  const date = new Date(dateString).getTime();
  const diffMs = now - date;
  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMinutes < 1) return '< 1 min';
  if (diffMinutes < 60) return `${diffMinutes} min`;
  if (diffHours < 24) return `${diffHours}h`;
  return `${diffDays}d`;
}

export function DriveSourceCard({ source, onSync, onUnlink, syncing }: DriveSourceCardProps) {
  const { t } = useTranslation();
  const statusDisplay = getSyncStatusDisplay(source.sync_status);

  return (
    <Card className="group">
      <CardContent className="p-4 flex items-center gap-3">
        {/* Folder icon */}
        <div className="shrink-0 rounded-lg bg-primary/10 p-2">
          <FolderSync className="h-4 w-4 text-primary" />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{source.folder_name}</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
            <Badge variant={statusDisplay.variant} size="sm" icon={statusDisplay.icon}>
              {t(statusDisplay.key)}
            </Badge>
            <span>
              {t('spaces.drive.synced_count', { count: source.synced_file_count })}
              {' / '}
              {t('spaces.drive.files_count', { count: source.file_count })}
            </span>
            {source.last_sync_at && (
              <>
                <span>&middot;</span>
                <span>
                  {t('spaces.drive.last_synced', {
                    time: formatRelativeTime(source.last_sync_at),
                  })}
                </span>
              </>
            )}
          </div>
          {source.sync_status === 'error' && source.error_message && (
            <p className="mt-1 text-xs text-destructive truncate">{source.error_message}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => onSync(source.id)}
            disabled={syncing || source.sync_status === 'syncing'}
            title={t('spaces.drive.sync_now')}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"
            onClick={() => onUnlink(source.id)}
            title={t('spaces.drive.unlink')}
          >
            <Unlink className="h-3.5 w-3.5 text-destructive" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
