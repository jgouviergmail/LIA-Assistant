'use client';

/**
 * A repository holding several skills: the reader picks the folder (ADR-327).
 * Each folder is a native button; the root of the repository is named in words.
 */
import type { TFunction } from 'i18next';
import { ArrowLeft, Folder } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { LibraryFolderChoice as Choice } from '@/lib/skill-library/types';

export function LibraryFolderChoice({
  choice,
  busy,
  t,
  onPick,
  onBack,
}: {
  choice: Choice;
  busy: boolean;
  t: TFunction;
  onPick: (path: string) => void;
  onBack: () => void;
}) {
  return (
    <div className="space-y-3" aria-busy={busy}>
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <Folder className="h-4 w-4 text-primary" aria-hidden />
        {t('settings.skills.library.address.choose', {
          count: choice.folders.length,
          repository: choice.repository,
        })}
      </h3>
      <ul className="space-y-2">
        {choice.folders.map(folder => (
          <li key={folder}>
            <Button
              variant="outline"
              className="h-auto w-full justify-start break-all py-2 text-left font-mono text-xs"
              onClick={() => {
                if (!busy) onPick(folder);
              }}
              aria-disabled={busy}
            >
              {folder || t('settings.skills.library.address.root')}
            </Button>
          </li>
        ))}
      </ul>
      <Button variant="outline" onClick={onBack} className="gap-1.5">
        <ArrowLeft className="h-4 w-4" aria-hidden />
        {t('settings.skills.library.preview.back')}
      </Button>
    </div>
  );
}
