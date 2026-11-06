'use client';

/**
 * FileOrganizer — a new folder, a rename, a move, a copy (ADR-369, lot 6).
 *
 * The screen says which act is under way; this runs it and tells how it went. What
 * adds an item carries ONE key for as long as its dialog stays open: a second press
 * after a lost answer is told what became of the first, never run again, and a
 * refusal frees the key for another try. A copy the provider finishes after
 * answering is said as under way, never as done. A move that moved nothing leaves
 * the walk open, a name already held being said as such; a move that moved some
 * closes it, and what stayed stays ticked.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import type { WorkbenchFilesState } from '@/hooks/useWorkbenchFiles';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { actReport } from '@/lib/workbench/mail';
import type {
  WorkbenchActOutcome,
  WorkbenchDriveItem,
  WorkbenchFileAncestor,
} from '@/lib/workbench/types';

import { FileNameDialog } from './FileNameDialog';
import { FileShareDialog } from './FileShareDialog';
import { FolderPicker } from './FolderPicker';
import { generateUUID } from '@/lib/utils';

type Named = Pick<WorkbenchDriveItem, 'id' | 'name'>;

/** Where a walk starts, and the folder a move leaves (left out, nobody knows). */
export interface FilePlace {
  trail: readonly WorkbenchFileAncestor[];
  from: string | null | undefined;
}

/** The act under way. */
export type FileAct =
  | { kind: 'folder' }
  | { kind: 'rename'; item: Named }
  | { kind: 'move'; items: readonly Named[]; place: FilePlace }
  | { kind: 'copy'; item: Named; place: FilePlace }
  | { kind: 'share'; item: Named };

export interface FileOrganizerProps {
  lng: Language;
  provider: string | null;
  act: FileAct | null;
  /** The folder the list stands in: a new one goes there. */
  folderId: string | null;
  /** The longest name the routes take. */
  nameMax: number | undefined;
  state: Pick<WorkbenchFilesState, 'createFolder' | 'rename' | 'move' | 'copy'>;
  onClose: () => void;
  /** An item changed: what shows it reads it again. */
  onChanged: () => void;
  /** A selection moved, all or part. */
  onMoved: (outcome: WorkbenchActOutcome) => void;
}

export function FileOrganizer(props: FileOrganizerProps) {
  const { act } = props;
  if (!act) return null;
  if (act.kind === 'folder') return <NewFolder {...props} />;
  if (act.kind === 'rename') return <Rename {...props} act={act} />;
  if (act.kind === 'move') return <Move {...props} act={act} />;
  if (act.kind === 'share') {
    return <FileShareDialog lng={props.lng} file={act.item} onClose={props.onClose} />;
  }
  return <Copy {...props} act={act} />;
}

/** Whether an act went through, a refusal said in its own words: its dialog stays. */
function useSaid(lng: Language) {
  const { t } = useTranslation(lng);
  return async (run: () => Promise<boolean>): Promise<boolean> => {
    try {
      return await run();
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
      return false;
    }
  };
}

function NewFolder({ lng, folderId, nameMax, state, onClose }: FileOrganizerProps) {
  const { t } = useTranslation(lng);
  const said = useSaid(lng);
  const [key] = useState(() => generateUUID());
  return (
    <FileNameDialog
      lng={lng}
      title={t('workbench.files.new_folder')}
      submitLabel={t('workbench.files.create')}
      initial=""
      maxLength={nameMax}
      onClose={onClose}
      onSubmit={name =>
        said(async () => {
          await state.createFolder(name, folderId, key);
          toast.success(t('workbench.files.folder_made'));
          return true;
        })
      }
    />
  );
}

function Rename({
  lng,
  nameMax,
  state,
  act,
  onClose,
  onChanged,
}: FileOrganizerProps & { act: Extract<FileAct, { kind: 'rename' }> }) {
  const { t } = useTranslation(lng);
  const said = useSaid(lng);
  return (
    <FileNameDialog
      lng={lng}
      title={t('workbench.files.rename_title', { name: act.item.name })}
      submitLabel={t('workbench.files.rename')}
      initial={act.item.name}
      maxLength={nameMax}
      onClose={onClose}
      onSubmit={name =>
        said(async () => {
          await state.rename(act.item.id, name);
          onChanged();
          toast.success(t('workbench.files.renamed'));
          return true;
        })
      }
    />
  );
}

function Move({
  lng,
  provider,
  state,
  act,
  onClose,
  onChanged,
  onMoved,
}: FileOrganizerProps & { act: Extract<FileAct, { kind: 'move' }> }) {
  const { t } = useTranslation(lng);
  const said = useSaid(lng);
  const ids = act.items.map(item => item.id);
  const [only] = act.items;
  const moveTo = async (folderId: string | null) => {
    const outcome = await state.move(ids, folderId);
    if (!outcome) return false;
    const { tone, done, failed } = actReport(outcome);
    const nameHeld = outcome.failed.some(item => item.status === 'name_taken');
    if (tone === 'success') toast.success(t('workbench.files.moved', { count: done }));
    else if (tone === 'failed' && nameHeld) toast.error(t('workbench.errors.name_taken'));
    else toast.error(t('workbench.files.partial', { done, failed }));
    if (tone === 'failed') return false;
    onChanged();
    onMoved(outcome);
    return true;
  };
  return (
    <FolderPicker
      lng={lng}
      provider={provider}
      title={
        ids.length === 1 && only
          ? t('workbench.files.move_title', { name: only.name })
          : t('workbench.files.move_many_title', { count: ids.length })
      }
      submitLabel={t('workbench.files.move_here')}
      trail={act.place.trail}
      leaving={ids}
      from={act.place.from}
      onClose={onClose}
      onPick={folderId => said(() => moveTo(folderId))}
    />
  );
}

function Copy({
  lng,
  provider,
  nameMax,
  state,
  act,
  onClose,
}: FileOrganizerProps & { act: Extract<FileAct, { kind: 'copy' }> }) {
  const { t } = useTranslation(lng);
  const said = useSaid(lng);
  const [key] = useState(() => generateUUID());
  const initial = t('workbench.files.copy_name', { name: act.item.name }).slice(0, nameMax);
  return (
    <FolderPicker
      lng={lng}
      provider={provider}
      title={t('workbench.files.copy_title', { name: act.item.name })}
      submitLabel={t('workbench.files.copy_here')}
      trail={act.place.trail}
      leaving={[]}
      name={{ initial, maxLength: nameMax }}
      onClose={onClose}
      onPick={(folderId, name) =>
        said(async () => {
          const copied = await state.copy(act.item.id, folderId, name, key);
          toast.success(t(copied?.item ? 'workbench.files.copied' : 'workbench.files.copying'));
          return true;
        })
      }
    />
  );
}
