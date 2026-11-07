'use client';

/**
 * FolderPicker — the folder a move or a copy goes to (ADR-369, lot 6).
 *
 * A walk from where the item sits, a folder at a time, up to the top of the drive.
 * Folders alone are offered, what is leaving never: a folder cannot go inside
 * itself, and what it holds cannot be reached without entering it. A folder's page
 * can hold files alone: the walk reads on. A move to where the items already sit
 * would do nothing, so it is not offered. A copy takes a name here too, since a
 * drive may refuse one a folder already holds. An act that did not go through
 * leaves the walk open, to choose another folder or another name.
 */
import { ArrowLeft, ChevronRight, Folder } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { FILES_PATH } from '@/hooks/useWorkbenchFiles';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { folderOf, isOneName } from '@/lib/workbench/files';
import { fileWord } from '@/lib/workbench/files-words';
import type { WorkbenchDriveItem, WorkbenchFileAncestor } from '@/lib/workbench/types';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface FolderPickerProps {
  lng: Language;
  provider: string | null;
  title: string;
  submitLabel: string;
  /** Where the walk starts, from the top down. */
  trail: readonly WorkbenchFileAncestor[];
  /** The ids on their way: never offered as a place. */
  leaving: readonly string[];
  /** The folder a move leaves (null at the top); left out, nowhere is ruled out. */
  from?: string | null;
  /** The copy's name, where the act takes one. */
  name?: { initial: string; maxLength: number | undefined };
  onClose: () => void;
  /** Whether the act went through; `name` is said when the act takes one. */
  onPick: (folderId: string | null, name: string | undefined) => Promise<boolean>;
}

export function FolderPicker({
  lng,
  provider,
  title,
  submitLabel,
  trail: start,
  leaving,
  from,
  name,
  onClose,
  onPick,
}: FolderPickerProps) {
  const [trail, setTrail] = useState<readonly WorkbenchFileAncestor[]>(start);
  const [typed, setTyped] = useState(name?.initial ?? '');
  const [busy, setBusy] = useState(false);
  const here = trail.at(-1) ?? null;
  const hereId = here?.id ?? null;
  const params = useMemo(() => (hereId ? { folder_id: hereId } : {}), [hereId]);
  const list = useWorkbenchPage<WorkbenchDriveItem>(FILES_PATH, params);
  const wanted = name ? typed.trim() : undefined;
  const nameRefused = wanted !== undefined && !isOneName(wanted);
  const unusable = from === hereId || wanted === '' || nameRefused;

  const pick = async () => {
    if (busy || unusable) return;
    setBusy(true);
    if (await onPick(hereId, wanted)) onClose();
    else setBusy(false);
  };

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-md">
        <ToolDialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </ToolDialogHeader>
        {name && (
          <CopyName
            lng={lng}
            value={typed}
            maxLength={name.maxLength}
            refused={nameRefused}
            onChange={setTyped}
          />
        )}
        <WalkHead
          lng={lng}
          provider={provider}
          here={here}
          onUp={() => setTrail(trail.slice(0, -1))}
        />
        <Folders
          lng={lng}
          list={list}
          leaving={leaving}
          onEnter={folder => setTrail([...trail, folder])}
        />
        <ToolActions>
          <CancelButton lng={lng} onClick={onClose} />
          <Button isLoading={busy} disabled={unusable} onClick={() => void pick()}>
            {submitLabel}
          </Button>
        </ToolActions>
      </DialogContent>
    </Dialog>
  );
}

/** The copy's name, refused here where a drive would refuse it there. */
function CopyName({
  lng,
  value,
  maxLength,
  refused,
  onChange,
}: {
  lng: Language;
  value: string;
  maxLength: number | undefined;
  refused: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-1">
      <Input
        aria-label={t('workbench.files.name_label')}
        aria-invalid={refused || undefined}
        value={value}
        maxLength={maxLength}
        onChange={event => onChange(event.target.value)}
      />
      {refused && (
        <p role="alert" className="text-sm text-destructive">
          {t('workbench.files.name_is_one')}
        </p>
      )}
    </div>
  );
}

/** Where the walk stands, and the way back up. */
function WalkHead({
  lng,
  provider,
  here,
  onUp,
}: {
  lng: Language;
  provider: string | null;
  here: WorkbenchFileAncestor | null;
  onUp: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex min-h-9 min-w-0 items-center gap-1 text-sm font-medium">
      {here && (
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('workbench.files.folder_up')}
          onClick={onUp}
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      <span className="min-w-0 truncate">
        {here ? here.name || t('workbench.files.no_name') : t(fileWord(provider, 'my_drive'))}
      </span>
    </div>
  );
}

function Folders({
  lng,
  list,
  leaving,
  onEnter,
}: {
  lng: Language;
  list: WorkbenchPageState<WorkbenchDriveItem>;
  leaving: readonly string[];
  onEnter: (folder: WorkbenchFileAncestor) => void;
}) {
  const { t } = useTranslation(lng);
  if (list.loading) {
    return (
      <div className="h-56 space-y-2 rounded-md border p-2" aria-busy="true">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }
  if (list.error && list.items.length === 0) {
    return (
      <div className="h-56 rounded-md border">
        <EmptyState
          description={t('workbench.files.read_failed')}
          action={{ label: t('workbench.states.retry'), onClick: () => void list.refresh() }}
        />
      </div>
    );
  }
  const offered = list.items.flatMap(item => {
    const id = folderOf(item);
    return id && !leaving.includes(id) && !leaving.includes(item.id)
      ? [{ id, name: item.name }]
      : [];
  });
  return (
    <div className="h-56 overflow-y-auto rounded-md border">
      <ul>
        {offered.map(folder => (
          <li key={folder.id}>
            <Button
              variant="ghost"
              className="h-10 w-full justify-start gap-2 rounded-none font-normal"
              onClick={() => onEnter(folder)}
            >
              <Folder className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-left">
                {folder.name || t('workbench.files.no_name')}
              </span>
              <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
      {offered.length === 0 && !list.nextToken && (
        <p className="p-4 text-center text-sm text-muted-foreground">
          {t('workbench.files.no_folders')}
        </p>
      )}
      {list.nextToken && (
        <div className="p-2">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            isLoading={list.loadingMore}
            onClick={() => void list.loadMore()}
          >
            {t('workbench.files.more')}
          </Button>
        </div>
      )}
    </div>
  );
}
