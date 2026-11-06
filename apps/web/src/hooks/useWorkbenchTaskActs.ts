'use client';

/**
 * What organises a list of tasks (ADR-369, lot 9), beside what writes one (`useWorkbenchTasks`).
 *
 * An act on a selection answers item by item: what it did leaves or changes on screen, what it
 * could not do stays. A task moved leaves the list it was in. Clearing and placing ask the
 * provider, so the listing is read again. A step changes on its task.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type {
  WorkbenchActOutcome,
  WorkbenchTask,
  WorkbenchTaskList,
  WorkbenchTaskMoveOutcome,
  WorkbenchTasksCleared,
  WorkbenchTaskStep,
} from '@/lib/workbench/types';

const LISTS_PATH = '/workbench/tasks/lists';
const TASKS_PATH = '/workbench/tasks';
const STEPS_PATH = `${TASKS_PATH}/steps`;
const NOTHING_DONE: WorkbenchActOutcome = { done: [], failed: [] };

export interface WorkbenchTaskActs {
  renameList: (list: WorkbenchTaskList, title: string) => Promise<void>;
  setCompleted: (ids: readonly string[], completed: boolean) => Promise<WorkbenchActOutcome>;
  remove: (ids: readonly string[]) => Promise<WorkbenchActOutcome>;
  move: (ids: readonly string[], destination: string) => Promise<WorkbenchActOutcome>;
  /** @returns What went, or nothing when no list is open. */
  clearCompleted: () => Promise<WorkbenchTasksCleared | undefined>;
  /** Puts a task after a sibling; null puts it first. */
  place: (task: WorkbenchTask, after: string | null) => Promise<void>;
  addStep: (task: WorkbenchTask, title: string, key: string) => Promise<void>;
  toggleStep: (task: WorkbenchTask, step: WorkbenchTaskStep) => Promise<void>;
  removeStep: (task: WorkbenchTask, step: WorkbenchTaskStep) => Promise<void>;
}

/**
 * @param listId - The open list.
 * @param lists - The account's lists.
 * @param tasks - The open list's tasks.
 */
export function useWorkbenchTaskActs(
  listId: string | null,
  lists: WorkbenchPageState<WorkbenchTaskList>,
  tasks: WorkbenchPageState<WorkbenchTask>
): WorkbenchTaskActs {
  const { replaceItem: replaceList } = lists;
  const { replaceItem: replaceTask, refresh: rereadTasks } = tasks;
  const { mutate: patch } = useApiMutation<object, unknown>({
    method: 'PATCH',
    componentName: 'WorkbenchTaskActs',
  });
  const { mutate: post } = useApiMutation<object, unknown>({
    method: 'POST',
    componentName: 'WorkbenchTaskActs',
  });
  const { mutate: drop } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchTaskActs',
  });

  const renameList = useCallback(
    async (list: WorkbenchTaskList, title: string) => {
      const saved = await patch(LISTS_PATH, { list_id: list.id, title });
      if (saved) replaceList(list.id, saved as WorkbenchTaskList);
    },
    [patch, replaceList]
  );

  const selection = useCallback(
    async (act: string, ids: readonly string[], extra: object) => {
      if (!listId) return NOTHING_DONE;
      const answer = await post(`${TASKS_PATH}/selection/${act}`, {
        list_id: listId,
        task_ids: ids,
        ...extra,
      });
      return (answer ?? NOTHING_DONE) as WorkbenchActOutcome;
    },
    [listId, post]
  );

  const setCompleted = useCallback(
    async (ids: readonly string[], completed: boolean) => {
      const outcome = await selection('completed', ids, { completed });
      await rereadTasks();
      return outcome;
    },
    [rereadTasks, selection]
  );

  const leaving = useCallback(
    (outcome: WorkbenchActOutcome) => {
      for (const id of outcome.done) replaceTask(id, null);
      return outcome;
    },
    [replaceTask]
  );

  const remove = useCallback(
    async (ids: readonly string[]) => leaving(await selection('delete', ids, {})),
    [leaving, selection]
  );

  const move = useCallback(
    async (ids: readonly string[], destination: string) =>
      leaving(
        (await selection('move', ids, {
          destination_list_id: destination,
        })) as WorkbenchTaskMoveOutcome
      ),
    [leaving, selection]
  );

  const clearCompleted = useCallback(async () => {
    if (!listId) return undefined;
    const cleared = await post(`${TASKS_PATH}/clear-completed`, { list_id: listId });
    await rereadTasks();
    return cleared as WorkbenchTasksCleared | undefined;
  }, [listId, post, rereadTasks]);

  const place = useCallback(
    async (task: WorkbenchTask, after: string | null) => {
      if (!listId) return;
      await post(`${TASKS_PATH}/place`, { list_id: listId, task_id: task.id, after });
      await rereadTasks();
    },
    [listId, post, rereadTasks]
  );

  const addStep = useCallback(
    async (task: WorkbenchTask, title: string, key: string) => {
      if (!listId) return;
      const step = await post(STEPS_PATH, {
        list_id: listId,
        task_id: task.id,
        title,
        idempotency_key: key,
      });
      if (step) {
        replaceTask(task.id, { ...task, steps: [...task.steps, step as WorkbenchTaskStep] });
      }
    },
    [listId, post, replaceTask]
  );

  const toggleStep = useCallback(
    async (task: WorkbenchTask, step: WorkbenchTaskStep) => {
      if (!listId) return;
      const saved = await patch(STEPS_PATH, {
        list_id: listId,
        task_id: task.id,
        step_id: step.id,
        checked: !step.checked,
      });
      if (saved) {
        const steps = task.steps.map(item =>
          item.id === step.id ? (saved as WorkbenchTaskStep) : item
        );
        replaceTask(task.id, { ...task, steps });
      }
    },
    [listId, patch, replaceTask]
  );

  const removeStep = useCallback(
    async (task: WorkbenchTask, step: WorkbenchTaskStep) => {
      if (!listId) return;
      await drop(STEPS_PATH, undefined, {
        params: { list_id: listId, task_id: task.id, step_id: step.id },
      });
      replaceTask(task.id, { ...task, steps: task.steps.filter(item => item.id !== step.id) });
    },
    [drop, listId, replaceTask]
  );

  return {
    renameList,
    setCompleted,
    remove,
    move,
    clearCompleted,
    place,
    addStep,
    toggleStep,
    removeStep,
  };
}
