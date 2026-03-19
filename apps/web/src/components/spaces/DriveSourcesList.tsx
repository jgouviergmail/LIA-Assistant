/**
 * List of linked Google Drive folder sources with link/unlink/sync actions.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FolderPlus, HardDriveDownload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DriveSourceCard } from './DriveSourceCard';
import { DriveFolderPickerDialog } from './DriveFolderPickerDialog';
import { UnlinkDriveSourceConfirm } from './UnlinkDriveSourceConfirm';
import type { RAGDriveSource } from '@/types/rag-spaces';

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
  const [pickerOpen, setPickerOpen] = useState(false);
  const [unlinkSource, setUnlinkSource] = useState<RAGDriveSource | null>(null);

  const handleSelect = async (folderId: string, folderName: string) => {
    await onLink(folderId, folderName);
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
          <HardDriveDownload className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">{t('spaces.drive.title')}</h3>
        </div>
        <Button
          variant="outline"
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
              onSync={onSync}
              onUnlink={id => {
                const found = sources.find(s => s.id === id);
                if (found) setUnlinkSource(found);
              }}
              syncing={syncing}
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
