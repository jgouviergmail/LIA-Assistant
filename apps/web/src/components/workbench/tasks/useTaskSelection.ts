'use client';

/**
 * Tasks ticked for one act (ADR-369, lot 9): the mode, what is ticked, and each act told as it
 * went. What was done leaves the selection; a task left in two lists is said in its own words,
 * because « not moved » would be false.
 */
import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import { useListSelection, type ListSelection } from '@/components/workbench/useListSelection';
import type { WorkbenchTaskActs } from '@/hooks/useWorkbenchTaskActs';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorkbenchActOutcome } from '@/lib/workbench/types';

export interface TaskSelection extends ListSelection {
  selecting: boolean;
  toggleSelecting: () => void;
  busy: boolean;
  setCompleted: (completed: boolean) => Promise<void>;
  remove: () => Promise<void>;
  move: (destination: string) => Promise<void>;
  /** Says what an act left undone. */
  report: (outcome: WorkbenchActOutcome) => void;
}

/**
 * @param lng - The reader's language.
 * @param listId - The open list: another one lets go of what was ticked.
 * @param acts - The screen's acts.
 * @param tell - Says a refusal of the whole act.
 */
export function useTaskSelection(
  lng: Language,
  listId: string | null,
  acts: WorkbenchTaskActs,
  tell: (error: unknown) => void
): TaskSelection {
  const { t } = useTranslation(lng);
  const selection = useListSelection(listId ?? '');
  const { selected, select } = selection;
  const [selecting, setSelecting] = useState(false);
  const [busy, setBusy] = useState(false);

  const report = useCallback(
    (outcome: WorkbenchActOutcome) => {
      if (outcome.failed.some(item => item.status === 'task_left_behind')) {
        toast.error(t('workbench.errors.task_left_behind'));
      } else if (outcome.failed.length > 0) {
        toast.error(t('workbench.tasks.partial'));
      }
    },
    [t]
  );

  const running = useCallback(
    async (act: () => Promise<WorkbenchActOutcome>) => {
      setBusy(true);
      try {
        const outcome = await act();
        report(outcome);
        select(new Set([...selected].filter(id => !outcome.done.includes(id))));
      } catch (error: unknown) {
        tell(error);
      } finally {
        setBusy(false);
      }
    },
    [report, select, selected, tell]
  );

  const ids = [...selected];
  return {
    ...selection,
    selecting,
    toggleSelecting: () => {
      setSelecting(on => !on);
      select(new Set());
    },
    busy,
    setCompleted: completed => running(() => acts.setCompleted(ids, completed)),
    remove: () => running(() => acts.remove(ids)),
    move: destination => running(() => acts.move(ids, destination)),
    report,
  };
}
