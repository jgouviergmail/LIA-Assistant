/**
 * Dialog for browsing and selecting a Google Drive folder.
 *
 * Uses breadcrumb navigation to traverse the folder hierarchy. The dialog
 * stays mounted while closed (its parent keeps it), so the listing is read
 * only while it is open, and read again at every opening.
 *
 * A failed listing keeps its message and its retry on screen while the retry
 * runs: the button that holds the focus is the one that reports the next
 * answer, a second failure included.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Folder, FileText, ChevronRight, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useDriveFolderBrowser, type DriveBreadcrumbEntry } from '@/hooks/useDriveSources';

interface DriveFolderPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  spaceId: string;
  onSelect: (folderId: string, folderName: string) => void;
}

export function DriveFolderPickerDialog({
  open,
  onOpenChange,
  spaceId,
  onSelect,
}: DriveFolderPickerDialogProps) {
  const { t } = useTranslation();
  const {
    folders,
    files,
    loading,
    error,
    breadcrumb,
    currentFolderId,
    navigateToFolder,
    navigateBack,
    reset,
    refetch,
  } = useDriveFolderBrowser(spaceId, open);

  // The root has no Drive name of its own: it reads in the person's language.
  const folderLabel = (entry: DriveBreadcrumbEntry) => entry.name ?? t('spaces.drive.picker_root');
  const currentFolderName = folderLabel(breadcrumb[breadcrumb.length - 1]);

  const handleSelect = useCallback(() => {
    onSelect(currentFolderId, currentFolderName);
    onOpenChange(false);
    reset();
  }, [currentFolderId, currentFolderName, onSelect, onOpenChange, reset]);

  const handleClose = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) {
        reset();
      }
      onOpenChange(isOpen);
    },
    [onOpenChange, reset]
  );

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('spaces.drive.picker_title')}</DialogTitle>
          <DialogDescription>{t('spaces.drive.picker_description')}</DialogDescription>
        </DialogHeader>

        {/* Breadcrumb */}
        <nav className="flex items-center gap-1 text-sm text-muted-foreground overflow-x-auto py-1">
          {breadcrumb.map((entry, index) => (
            <span key={entry.id} className="flex items-center gap-1 shrink-0">
              {index > 0 && <ChevronRight className="h-3 w-3" />}
              <button
                type="button"
                className={`hover:text-foreground transition-colors ${
                  index === breadcrumb.length - 1 ? 'text-foreground font-medium' : ''
                }`}
                onClick={() => navigateBack(index)}
                disabled={index === breadcrumb.length - 1}
              >
                {folderLabel(entry)}
              </button>
            </span>
          ))}
        </nav>

        {/* Folder list */}
        <div className="min-h-[200px] max-h-[320px] overflow-y-auto rounded-md border bg-card">
          {error ? (
            <div className="flex flex-col items-center justify-center py-12 text-sm text-destructive">
              <p>{t('spaces.drive.picker_error')}</p>
              {/* A retry of the SAME folder: the breadcrumb stays where it is,
                  and the busy button keeps the focus until the answer lands. */}
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                isLoading={loading}
                onClick={() => void refetch()}
              >
                {t('errors.try_again')}
              </Button>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner
                size="md"
                spinnerColor="muted"
                label={t('spaces.drive.picker_loading')}
              />
            </div>
          ) : folders.length === 0 && files.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-sm text-muted-foreground">
              <FolderOpen className="h-8 w-8 mb-2" />
              <p>{t('spaces.drive.picker_empty')}</p>
            </div>
          ) : (
            <ul className="divide-y">
              {folders.map(folder => (
                <li key={folder.id}>
                  <button
                    type="button"
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-accent/50 transition-colors text-left"
                    onClick={() => navigateToFolder(folder.id, folder.name)}
                  >
                    <Folder className="h-4 w-4 text-primary shrink-0" />
                    <span className="truncate">{folder.name}</span>
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground ml-auto shrink-0" />
                  </button>
                </li>
              ))}
              {files.map(file => (
                <li
                  key={file.id}
                  className="flex items-center gap-3 px-3 py-2.5 text-sm text-muted-foreground"
                >
                  <FileText className="h-4 w-4 shrink-0" />
                  <span className="truncate">{file.name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSelect} disabled={loading}>
            {t('spaces.drive.picker_select')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
