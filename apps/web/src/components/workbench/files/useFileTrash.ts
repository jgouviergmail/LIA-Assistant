'use client';

/**
 * What goes to the trash, comes back from it, and leaves for good (ADR-369, lot 6).
 *
 * Every act names what became of each file, and what could not be done stays ticked.
 * What just went to the trash can be taken back from the sentence that says so, on any
 * drive; the trash itself is listed where the drive allows it. Deleting for good and
 * emptying ask first, and belong to the person's hand alone (owner decision A2).
 */
import { toast } from 'sonner';

import type { ConfirmOptions } from '@/components/ui/use-confirm';
import type { WorkbenchFilesState } from '@/hooks/useWorkbenchFiles';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { fileWord } from '@/lib/workbench/files-words';
import { actReport } from '@/lib/workbench/mail';
import type { WorkbenchActOutcome, WorkbenchFileDetail } from '@/lib/workbench/types';

interface FileTrashProps {
  lng: Language;
  provider: string | null;
  state: Pick<WorkbenchFilesState, 'trash' | 'restore' | 'deleteForever' | 'emptyTrash'>;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  selected: ReadonlySet<string>;
  select: (ids: ReadonlySet<string>) => void;
  /** The file open in the detail. */
  openFile: string | null;
  closeFile: () => void;
}

export type FileTrash = ReturnType<typeof useFileTrash>;

export function useFileTrash({
  lng,
  provider,
  state,
  confirm,
  selected,
  select,
  openFile,
  closeFile,
}: FileTrashProps) {
  const { t } = useTranslation(lng);

  const refused = (error: unknown) => {
    const refusal = workbenchRefusal(error);
    toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.files.failed'));
  };

  /** What stays ticked, and the file that left the detail. */
  const settled = (ids: readonly string[], outcome: WorkbenchActOutcome) => {
    select(new Set([...selected].filter(id => !outcome.done.includes(id))));
    if (openFile && ids.includes(openFile) && outcome.done.includes(openFile)) closeFile();
  };

  const restore = async (ids: string[], settle = settled) => {
    try {
      const outcome = await state.restore(ids);
      if (!outcome) return;
      settle(ids, outcome);
      const { tone, done, failed } = actReport(outcome);
      if (tone === 'success') toast.success(t('workbench.files.restored', { count: done }));
      else toast.error(t('workbench.files.partial', { done, failed }));
    } catch (error: unknown) {
      refused(error);
    }
  };

  /** Later than the act: what is ticked and open by then is none of its business. */
  const undo = (ids: string[]) => ({
    action: {
      label: t('workbench.files.undo'),
      onClick: () => void restore(ids, () => undefined),
    },
  });

  const toTrash = async (ids: string[], title: string) => {
    const confirmed = await confirm({
      title,
      description: t(fileWord(provider, 'trash_description')),
      confirmLabel: t('workbench.files.trash'),
    });
    if (!confirmed) return;
    try {
      const outcome = await state.trash(ids);
      if (!outcome) return;
      settled(ids, outcome);
      const { tone, done, failed } = actReport(outcome);
      if (tone === 'success') {
        const sentence = ids.length === 1 ? 'trashed' : 'trashed_many';
        toast.success(t(`workbench.files.${sentence}`, { count: done }), undo(ids));
      } else toast.error(t('workbench.files.partial', { done, failed }));
    } catch (error: unknown) {
      refused(error);
    }
  };

  const forGood = async (ids: string[], title: string) => {
    const confirmed = await confirm({
      title,
      description: t('workbench.files.delete_description'),
      confirmLabel: t('workbench.files.delete_forever'),
    });
    if (!confirmed) return;
    try {
      const outcome = await state.deleteForever(ids);
      if (!outcome) return;
      settled(ids, outcome);
      const { tone, done, failed } = actReport(outcome);
      if (tone === 'success') toast.success(t('workbench.files.deleted', { count: done }));
      else toast.error(t('workbench.files.partial', { done, failed }));
    } catch (error: unknown) {
      refused(error);
    }
  };

  const named = (file: WorkbenchFileDetail) => ({
    name: file.name || t('workbench.files.no_name'),
  });
  const ticked = () => [...selected];

  return {
    trashOpen: (file: WorkbenchFileDetail) =>
      toTrash([file.id], t('workbench.files.trash_title', named(file))),
    trashTicked: () =>
      toTrash(ticked(), t('workbench.files.trash_many_title', { count: selected.size })),
    restoreOpen: (file: WorkbenchFileDetail) => restore([file.id]),
    restoreTicked: () => restore(ticked()),
    deleteOpen: (file: WorkbenchFileDetail) =>
      forGood([file.id], t('workbench.files.delete_title', named(file))),
    deleteTicked: () =>
      forGood(ticked(), t('workbench.files.delete_many_title', { count: selected.size })),
    empty: async () => {
      const confirmed = await confirm({
        title: t('workbench.files.empty_trash_title'),
        description: t('workbench.files.delete_description'),
        confirmLabel: t('workbench.files.empty_trash'),
      });
      if (!confirmed) return;
      try {
        await state.emptyTrash();
        select(new Set());
        closeFile();
        toast.success(t('workbench.files.emptied'));
      } catch (error: unknown) {
        refused(error);
      }
    },
  };
}
