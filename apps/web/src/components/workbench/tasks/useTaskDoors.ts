'use client';

/**
 * The acts of the tasks screen that ask first or tell after (ADR-369, lot 9): a question before
 * what cannot be brought back, and a toast for how it went.
 */
import { toast } from 'sonner';

import type { UseConfirmReturn } from '@/components/ui/use-confirm';
import type { WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import type { WorkbenchTaskActs } from '@/hooks/useWorkbenchTaskActs';
import type { WorkbenchTasksState } from '@/hooks/useWorkbenchTasks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { ViewTask, ViewTasks, WorkbenchTask, WorkbenchTaskList } from '@/lib/workbench/types';

import type { TaskSelection } from './useTaskSelection';

export interface TaskDoorsOptions {
  lng: Language;
  acts: WorkbenchTaskActs;
  state: WorkbenchTasksState;
  selection: TaskSelection;
  viewRead: WorkbenchItemState<ViewTasks>;
  openList: WorkbenchTaskList | null;
  confirm: UseConfirmReturn['confirm'];
  /** Says a refusal. */
  tell: (error: unknown) => void;
  /** Runs an act and says its refusal, then rethrows it. */
  act: (run: () => Promise<unknown>) => Promise<void>;
  onListGone: () => void;
  onTaskGone: () => void;
}

export interface TaskDoors {
  deleteList: () => Promise<void>;
  clearDone: () => Promise<void>;
  removeSelected: () => Promise<void>;
  moveOpen: (task: WorkbenchTask, destination: string) => Promise<void>;
  completeDue: (task: ViewTask) => void;
}

export function useTaskDoors({
  lng,
  acts,
  state,
  selection,
  viewRead,
  openList,
  confirm,
  tell,
  act,
  onListGone,
  onTaskGone,
}: TaskDoorsOptions): TaskDoors {
  const { t } = useTranslation(lng);
  return {
    deleteList: async () => {
      if (!openList) return;
      const confirmed = await confirm({
        title: t('workbench.tasks.delete_list_title', { name: openList.title }),
        description: t('workbench.tasks.delete_list_description'),
        confirmLabel: t('common.delete'),
      });
      if (!confirmed) return;
      try {
        await act(() => state.removeList(openList));
        onListGone();
      } catch {
        // Said by `act`; the list stays open.
      }
    },
    clearDone: async () => {
      const confirmed = await confirm({
        title: t('workbench.tasks.clear_completed_title'),
        description: t('workbench.tasks.clear_completed_description'),
        confirmLabel: t('common.delete'),
      });
      if (!confirmed) return;
      try {
        const cleared = await acts.clearCompleted();
        if (cleared) {
          const said = cleared.remaining
            ? 'workbench.tasks.cleared_more'
            : 'workbench.tasks.cleared';
          toast.success(t(said, { count: cleared.deleted }));
        }
      } catch (error: unknown) {
        tell(error);
      }
    },
    removeSelected: async () => {
      const confirmed = await confirm({
        title: t('workbench.tasks.delete_selection_title', { count: selection.selected.size }),
        description: t('workbench.tasks.delete_task_description'),
        confirmLabel: t('common.delete'),
      });
      if (confirmed) await selection.remove();
    },
    moveOpen: async (task, destination) => {
      try {
        const outcome = await acts.move([task.id], destination);
        selection.report(outcome);
        if (outcome.done.includes(task.id)) onTaskGone();
      } catch (error: unknown) {
        tell(error);
      }
    },
    completeDue: task => {
      void act(async () => {
        await state.completeDue(task);
        await viewRead.refresh();
      }).catch(() => undefined);
    },
  };
}
