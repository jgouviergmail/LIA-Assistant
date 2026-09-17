/**
 * List of linked Google Drive folder sources with link/unlink/sync actions.
 *
 * A sync is preceded by its count: the folder is synchronised WITH its
 * sub-folders, so the list asks the API what one sync would index and, past
 * the threshold the API publishes, shows the exact figures for the person to
 * confirm or cancel (`DriveSyncConfirmDialog`). Under the threshold the sync
 * starts at once; a count the API cannot compute starts nothing.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderPlus, HardDriveDownload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useDrivePreflight } from '@/hooks/useDriveSources';
import { DriveSourceCard } from './DriveSourceCard';
import { DriveFolderPickerDialog } from './DriveFolderPickerDialog';
import { DriveSyncConfirmDialog } from './DriveSyncConfirmDialog';
import { UnlinkDriveSourceConfirm } from './UnlinkDriveSourceConfirm';
import type { RAGDrivePreflight, RAGDriveSource } from '@/types/rag-spaces';

/** A sync waiting for the person's word, with the figures it was shown. */
interface PendingSync {
  source: RAGDriveSource;
  report: RAGDrivePreflight;
}

interface DriveSourcesListProps {
  spaceId: string;
  sources: RAGDriveSource[];
  onLink: (folderId: string, folderName: string) => Promise<unknown>;
  onUnlink: (sourceId: string, deleteDocuments: boolean) => void;
  onSync: (sourceId: string) => void;
  linking?: boolean;
  syncing?: boolean;
}

export function DriveSourcesList({
  spaceId,
  sources,
  onLink,
  onUnlink,
  onSync,
  linking,
  syncing,
}: DriveSourcesListProps) {
  const { t } = useTranslation();
  const { preflightFolder } = useDrivePreflight(spaceId);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [unlinkSource, setUnlinkSource] = useState<RAGDriveSource | null>(null);
  const [pendingSync, setPendingSync] = useState<PendingSync | null>(null);
  // The source being counted: a count walks the Drive, so a second click
  // while one runs must not start another (the row shows the busy state).
  const [countingId, setCountingId] = useState<string | null>(null);

  const handleSelect = async (folderId: string, folderName: string) => {
    await onLink(folderId, folderName);
  };

  const handleSyncRequest = useCallback(
    async (sourceId: string) => {
      const source = sources.find(s => s.id === sourceId);
      if (!source || countingId !== null) return;
      setCountingId(sourceId);
      let report: RAGDrivePreflight;
      try {
        report = await preflightFolder(sourceId);
      } catch {
        toast.error(t('spaces.drive.preflight_error'));
        return;
      } finally {
        setCountingId(null);
      }
      if (report.requires_confirmation) {
        setPendingSync({ source, report });
        return;
      }
      onSync(sourceId);
    },
    [sources, preflightFolder, onSync, t, countingId]
  );

  const handleSyncConfirm = () => {
    if (pendingSync) {
      onSync(pendingSync.source.id);
      setPendingSync(null);
    }
  };

  const handleUnlinkConfirm = (deleteDocuments: boolean) => {
    if (unlinkSource) {
      onUnlink(unlinkSource.id, deleteDocuments);
      setUnlinkSource(null);
    }
  };

  return (
    <div className="space-y-3">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HardDriveDownload className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-medium">{t('spaces.drive.title')}</h3>
        </div>
        <Button
          size="sm"
          className="gap-1.5"
          onClick={() => setPickerOpen(true)}
          isLoading={linking}
        >
          <FolderPlus className="h-3.5 w-3.5" />
          {t('spaces.drive.link_folder')}
        </Button>
      </div>

      {/* Sources list or empty state */}
      {sources.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center">
          <p className="text-sm text-muted-foreground">{t('spaces.drive.empty')}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map(source => (
            <DriveSourceCard
              key={source.id}
              source={source}
              onSync={sourceId => void handleSyncRequest(sourceId)}
              onUnlink={id => {
                const found = sources.find(s => s.id === id);
                if (found) setUnlinkSource(found);
              }}
              syncing={syncing || countingId === source.id}
            />
          ))}
        </div>
      )}

      {/* Picker dialog */}
      <DriveFolderPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        spaceId={spaceId}
        onSelect={handleSelect}
      />

      {/* Sync confirmation: the exact count past the threshold */}
      {pendingSync && (
        <DriveSyncConfirmDialog
          open={!!pendingSync}
          onOpenChange={open => {
            if (!open) setPendingSync(null);
          }}
          folderName={pendingSync.source.folder_name}
          report={pendingSync.report}
          onConfirm={handleSyncConfirm}
        />
      )}

      {/* Unlink confirmation dialog */}
      {unlinkSource && (
        <UnlinkDriveSourceConfirm
          open={!!unlinkSource}
          onOpenChange={open => {
            if (!open) setUnlinkSource(null);
          }}
          folderName={unlinkSource.folder_name}
          onConfirm={handleUnlinkConfirm}
        />
      )}
    </div>
  );
}
