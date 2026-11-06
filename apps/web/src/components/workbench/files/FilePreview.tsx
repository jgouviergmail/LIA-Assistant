'use client';

/**
 * FilePreview — a file read in the page (ADR-369, lots 6 and 14).
 *
 * The API answers the best a file can be read as, and `ShownDocument` holds a viewer for each; what
 * it shows can take a window. A file with nothing to show shows nothing, without a word: its
 * downloads stay right below. A reading that failed says so and can be tried again. Another file
 * opened drops the read under way.
 */
import { Maximize2 } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useShownDocument } from '@/hooks/useShownDocument';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchFileDetail } from '@/lib/workbench/types';

import { ShownReading } from '../ShownDocument';

const PREVIEW_PATH = '/workbench/files/preview';

export function FilePreview({ lng, file }: { lng: Language; file: WorkbenchFileDetail }) {
  const { t } = useTranslation(lng);
  const [large, setLarge] = useState(false);
  const read = useShownDocument(file.previewable ? PREVIEW_PATH : null, { id: file.id });
  const { kind } = read.state;

  if (!file.previewable || kind === 'none') return null;
  const seen = kind !== 'loading' && kind !== 'failed';
  return (
    <div className="space-y-2">
      <ShownReading lng={lng} read={read} name={file.name} />
      {seen && (
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setLarge(true)}>
          <Maximize2 className="h-4 w-4" aria-hidden="true" />
          {t('workbench.files.preview_enlarge')}
        </Button>
      )}
      {large && seen && (
        <Dialog open onOpenChange={open => !open && setLarge(false)}>
          <DialogContent className="sm:max-w-5xl">
            <DialogHeader>
              <DialogTitle className="truncate">{file.name}</DialogTitle>
              <DialogDescription className="sr-only">
                {t('workbench.files.preview_enlarge')}
              </DialogDescription>
            </DialogHeader>
            <ShownReading lng={lng} read={read} name={file.name} large />
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
