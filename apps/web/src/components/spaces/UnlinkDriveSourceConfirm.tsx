/**
 * Confirmation dialog for unlinking a Google Drive folder source.
 *
 * Follows the DeleteSpaceConfirm pattern (AlertDialog).
 * Includes an option to also delete synced documents.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface UnlinkDriveSourceConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folderName: string;
  onConfirm: (deleteDocuments: boolean) => void;
}

export function UnlinkDriveSourceConfirm({
  open,
  onOpenChange,
  folderName,
  onConfirm,
}: UnlinkDriveSourceConfirmProps) {
  const { t } = useTranslation();
  const [deleteDocuments, setDeleteDocuments] = useState(false);

  const handleConfirm = () => {
    onConfirm(deleteDocuments);
    setDeleteDocuments(false);
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setDeleteDocuments(false);
    }
    onOpenChange(isOpen);
  };

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('spaces.drive.unlink_confirm_title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('spaces.drive.unlink_confirm_message', { name: folderName })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <label className="flex items-center gap-2 text-sm cursor-pointer select-none px-1">
          <input
            type="checkbox"
            // aria-labelledby: the wrapping <label> already names this control
            // implicitly (valid per WCAG); the explicit reference makes the
            // name visible to static analysis too (F012).
            aria-labelledby="unlink-delete-docs-label"
            checked={deleteDocuments}
            onChange={e => setDeleteDocuments(e.target.checked)}
            className="rounded border-input h-4 w-4 accent-destructive"
          />
          <span id="unlink-delete-docs-label">{t('spaces.drive.unlink_delete_docs')}</span>
        </label>

        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={handleConfirm}>
            {t('spaces.drive.unlink')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
