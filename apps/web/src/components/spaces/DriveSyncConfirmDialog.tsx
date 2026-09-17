/**
 * « N files will be indexed — continue? »
 *
 * A Drive folder is synchronised WITH its sub-folders, so one click may
 * index far more than the folder shows. Past the threshold the API
 * publishes, the exact figures of the preflight are laid out — the count is
 * the subject, the breakdown says where it comes from — and the person
 * confirms or cancels. A cut walk says « at least »; new files the space has
 * no room for are named rather than silently left out.
 */

'use client';

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
import type { RAGDrivePreflight } from '@/types/rag-spaces';

interface DriveSyncConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folderName: string;
  report: RAGDrivePreflight;
  onConfirm: () => void;
}

export function DriveSyncConfirmDialog({
  open,
  onOpenChange,
  folderName,
  report,
  onConfirm,
}: DriveSyncConfirmDialogProps) {
  const { t } = useTranslation();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('spaces.drive.confirm.title', { name: folderName })}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p className="text-foreground font-medium">
                {t('spaces.drive.confirm.to_index', { count: report.to_index })}
                {report.truncated ? ` ${t('spaces.drive.confirm.truncated')}` : ''}
              </p>
              <p>
                {t('spaces.drive.confirm.breakdown', {
                  new: report.new,
                  modified: report.modified,
                  unchanged: report.unchanged,
                  unsupported: report.unsupported,
                  folders: report.folders,
                })}
              </p>
              {report.over_capacity > 0 && (
                <p>{t('spaces.drive.confirm.over_capacity', { count: report.over_capacity })}</p>
              )}
              {report.unreadable_folders > 0 && (
                <p>
                  {t('spaces.drive.confirm.unreadable_folders', {
                    count: report.unreadable_folders,
                  })}
                </p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t('spaces.drive.confirm.confirm')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
