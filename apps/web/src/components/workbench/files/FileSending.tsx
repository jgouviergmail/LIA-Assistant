'use client';

/**
 * What the list says of files on their way, and takes when they are dropped (ADR-369,
 * lot 6).
 *
 * A drag of anything but files is left alone. A folder dropped reaches the page as an
 * empty file nothing can read, so it is told apart and said; below `lg` nothing drags,
 * and « Send » does the same.
 */
import { useState, type DragEvent } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

import type { UploadNow } from '../useUploadQueue';

function holdsFiles(event: DragEvent): boolean {
  return [...event.dataTransfer.types].includes('Files');
}

/** The files of a drop, and whether a folder was among them. */
function droppedFiles(transfer: DataTransfer): { files: File[]; folders: boolean } {
  const items = [...transfer.items];
  const isFolder = (index: number) => items[index]?.webkitGetAsEntry()?.isDirectory === true;
  const all = [...transfer.files];
  return {
    files: all.filter((_, index) => !isFolder(index)),
    folders: all.some((_, index) => isFolder(index)),
  };
}

/** The list takes a drop while it stands in a folder. */
export function useFileDrop({
  lng,
  enabled,
  onFiles,
}: {
  lng: Language;
  enabled: boolean;
  onFiles: (files: File[]) => void;
}) {
  const { t } = useTranslation(lng);
  const [dragging, setDragging] = useState(false);
  const handlers = {
    onDragOver: (event: DragEvent) => {
      if (!enabled || !holdsFiles(event)) return;
      event.preventDefault();
      setDragging(true);
    },
    onDragLeave: (event: DragEvent) => {
      const within = event.relatedTarget instanceof Node;
      if (!within || !event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false);
    },
    onDrop: (event: DragEvent) => {
      setDragging(false);
      if (!enabled || !holdsFiles(event)) return;
      event.preventDefault();
      const { files, folders } = droppedFiles(event.dataTransfer);
      if (folders) toast.error(t('workbench.files.send_no_folders'));
      if (files.length > 0) onFiles(files);
    },
  };
  return { dragging, handlers };
}

/** What is on its way, how far, and the way to stop it. */
export function FileSendingLine({
  lng,
  now,
  onStop,
}: {
  lng: Language;
  now: UploadNow;
  onStop: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex items-center gap-2 border-b px-3 py-1.5 text-sm">
      <span className="min-w-0 flex-1 truncate">
        {t('workbench.files.sending', {
          name: now.name,
          position: now.position,
          total: now.total,
        })}
      </span>
      <progress
        className="h-1.5 w-16 shrink-0 accent-primary"
        max={100}
        value={now.percent}
        aria-label={t('workbench.files.sending_progress')}
      />
      <Button type="button" variant="ghost" size="sm" onClick={onStop}>
        {t('workbench.files.stop_sending')}
      </Button>
    </div>
  );
}
