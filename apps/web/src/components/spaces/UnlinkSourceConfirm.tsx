/**
 * Unlink a sync source — a Drive folder, a Gmail label (ADR-262).
 *
 * One dialog for both: the wording is passed in, the contract is not. The
 * checkbox that also deletes the synced documents carries a programmatic
 * accessible name (audit F012) and resets after each confirmation, so a
 * second unlink never inherits the first one's choice.
 */

'use client';

import { useId, useState } from 'react';
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

export interface UnlinkSourceConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  message: string;
  deleteDocumentsLabel: string;
  confirmLabel: string;
  onConfirm: (deleteDocuments: boolean) => void;
}

export function UnlinkSourceConfirm({
  open,
  onOpenChange,
  title,
  message,
  deleteDocumentsLabel,
  confirmLabel,
  onConfirm,
}: UnlinkSourceConfirmProps) {
  const { t } = useTranslation();
  const [deleteDocuments, setDeleteDocuments] = useState(false);
  const labelId = useId();

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
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{message}</AlertDialogDescription>
        </AlertDialogHeader>

        <label className="flex items-center gap-2 text-sm cursor-pointer select-none px-1">
          <input
            type="checkbox"
            // aria-labelledby: the wrapping <label> already names this control
            // implicitly (valid per WCAG); the explicit reference makes the
            // name visible to static analysis too (F012).
            aria-labelledby={labelId}
            checked={deleteDocuments}
            onChange={e => setDeleteDocuments(e.target.checked)}
            className="rounded border-input h-4 w-4 accent-destructive"
          />
          <span id={labelId}>{deleteDocumentsLabel}</span>
        </label>

        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={handleConfirm}>
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
