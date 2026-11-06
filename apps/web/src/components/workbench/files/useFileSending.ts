'use client';

/**
 * Files sent to the drive (ADR-369, lot 6).
 *
 * Each file keeps the folder it was given for and its own submission key. A file past
 * the published ceiling is said and never read. The list is read again once, at the end,
 * and what went is said.
 */
import { useCallback } from 'react';
import { toast } from 'sonner';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { fileSize } from '@/lib/workbench/mail';
import type { WorkbenchDriveItem } from '@/lib/workbench/types';

import { useUploadQueue, type Upload, type UploadTally } from '../useUploadQueue';
import { generateUUID } from '@/lib/utils';

const UPLOAD_PATH = '/workbench/files/upload';

function formOf({ file, place: folderId }: Upload<string | null>): FormData {
  const form = new FormData();
  form.append('name', file.name);
  form.append('idempotency_key', generateUUID());
  if (folderId) form.append('folder_id', folderId);
  form.append('file', file);
  return form;
}

export function useFileSending({
  lng,
  maxBytes,
  onSent,
}: {
  lng: Language;
  /** The published ceiling. */
  maxBytes: number;
  /** Something reached the drive: the list reads it. */
  onSent: () => void;
}) {
  const { t } = useTranslation(lng);

  const closing = useCallback(
    (tally: UploadTally) => {
      // A file stopped on its way may have arrived: the list says.
      if (tally.sent > 0 || tally.stopped) onSent();
      if (tally.stopped) toast.error(t('workbench.files.send_stopped', { count: tally.sent }));
      else if (tally.failed === 0) toast.success(t('workbench.files.sent', { count: tally.sent }));
      else if (tally.sent === 0 && tally.failed === 1) {
        const { refusal } = tally;
        toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
      } else {
        toast.error(t('workbench.files.sent_partial', { done: tally.sent, failed: tally.failed }));
      }
    },
    [onSent, t]
  );

  const { now, enqueue, stop } = useUploadQueue<string | null, WorkbenchDriveItem>({
    path: UPLOAD_PATH,
    formOf,
    onClosed: closing,
  });

  const send = useCallback(
    (files: readonly File[], folderId: string | null) => {
      const fitting = files.filter(file => file.size <= maxBytes);
      for (const file of files) {
        if (file.size > maxBytes) {
          toast.error(
            t('workbench.files.send_too_large', { name: file.name, max: fileSize(maxBytes, lng) })
          );
        }
      }
      enqueue(fitting.map(file => ({ file, place: folderId })));
    },
    [enqueue, lng, maxBytes, t]
  );

  return { now, send, stop };
}
