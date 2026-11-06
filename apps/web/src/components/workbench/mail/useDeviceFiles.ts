'use client';

/**
 * Files of the device brought to a message (ADR-369, lot 7.1).
 *
 * LIA keeps each one first, then it rides like any file of the person; its progress shows
 * and it can be stopped. What passes a bound is said and never read, a file still on its
 * way counting like one that arrived.
 */
import { useCallback, useRef } from 'react';
import { toast } from 'sonner';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { fileSize } from '@/lib/workbench/mail';
import { fittingFiles, type FileBounds, type FileOver } from '@/lib/workbench/mail-compose';
import type { AttachableFile } from '@/lib/workbench/types';

import { useUploadQueue, type Upload, type UploadTally } from '../useUploadQueue';

const KEEP_PATH = '/workbench/mail/files';

function formOf({ file }: Upload<null>): FormData {
  const form = new FormData();
  form.append('file', file);
  return form;
}

export function useDeviceFiles({
  lng,
  chosen,
  bounds,
  onKept,
}: {
  lng: Language;
  /** What the message already carries. */
  chosen: readonly { size: number }[];
  bounds: FileBounds;
  /** One file was kept: it is the message's now. */
  onKept: (file: AttachableFile) => void;
}) {
  const { t } = useTranslation(lng);
  const onTheirWay = useRef<{ size: number }[]>([]);

  const kept = useCallback(
    (file: AttachableFile) => {
      onTheirWay.current = onTheirWay.current.slice(1);
      onKept(file);
    },
    [onKept]
  );

  const closing = useCallback(
    ({ failed, refusal }: UploadTally) => {
      onTheirWay.current = [];
      if (failed === 0) return;
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
    },
    [t]
  );

  const { now, enqueue, stop } = useUploadQueue<null, AttachableFile>({
    path: KEEP_PATH,
    formOf,
    onAnswer: kept,
    onClosed: closing,
  });

  const said = (over: FileOver): string => {
    if (over.kind === 'count')
      return t('workbench.mail.files.max_files', { count: bounds.maxFiles });
    if (over.kind === 'bytes') {
      return t('workbench.mail.files.max_bytes', { max: fileSize(bounds.maxBytes, lng) });
    }
    return t('workbench.files.send_too_large', {
      name: over.name,
      max: fileSize(bounds.eachMaxBytes, lng),
    });
  };

  const send = (files: readonly File[]) => {
    const { fitting, over } = fittingFiles(files, [...chosen, ...onTheirWay.current], bounds);
    if (over) toast.error(said(over));
    onTheirWay.current = [...onTheirWay.current, ...fitting];
    enqueue(fitting.map(file => ({ file, place: null })));
  };

  return { now, send, stop };
}
