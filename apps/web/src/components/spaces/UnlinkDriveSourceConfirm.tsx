/**
 * Confirmation dialog for unlinking a Google Drive folder source.
 *
 * The dialog itself is shared with the Gmail label source (ADR-262):
 * `UnlinkSourceConfirm` owns the contract, this file owns the Drive wording.
 *
 * Phase: evolution — RAG Spaces (Google Drive sync)
 * Created: 2026-03-18
 */

'use client';

import { useTranslation } from 'react-i18next';

import { UnlinkSourceConfirm } from '@/components/spaces/UnlinkSourceConfirm';

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

  return (
    <UnlinkSourceConfirm
      open={open}
      onOpenChange={onOpenChange}
      title={t('spaces.drive.unlink_confirm_title')}
      message={t('spaces.drive.unlink_confirm_message', { name: folderName })}
      deleteDocumentsLabel={t('spaces.drive.unlink_delete_docs')}
      confirmLabel={t('spaces.drive.unlink')}
      onConfirm={onConfirm}
    />
  );
}
