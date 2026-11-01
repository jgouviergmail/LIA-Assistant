'use client';

/**
 * The tasks screen's reads and acts (ADR-369, Task 6.2).
 *
 * Two cursor listings (`useWorkbenchPage`): the account's lists, and the tasks
 * of the list asked for — the first list when none is (the address names a
 * list once the person picks one). Every act goes through `useApiMutation`:
 *
 * - a completion shows AT ONCE and is rolled back when the provider refuses it
 *   (the error is rethrown so the screen says why); a task whose completion is
 *   still on its way takes no second one;
 * - a new task or list carries the key of its submission (the caller keeps it
 *   until the act is done, so a second click is told, never sent twice), and
 *   the listing is re-read in place — the provider decides where it goes;
 * - a removed task or list leaves the listing, one already gone too; a task
 *   that had subtasks on screen re-reads the list, since the provider decides
 *   what becomes of them.
 */
import { useCallback, useRef, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useWorkbenchPage, type WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { WorkbenchTask, WorkbenchTaskList } from '@/lib/workbench/types';

const LISTS_PATH = '/workbench/tasks/lists';
const TASKS_PATH = '/workbench/tasks';
const NO_PARAMS = {};

/** A task to create in the open list (`schemas/tasks.NewTask`). */
export interface NewTaskBody {
  title: string;
  notes?: string;
  /** The day it is due, `YYYY-MM-DD`. */
  due?: string;
  /** The task it is a subtask of (Google only). */
  parent?: string;
  /** One key per submission, kept by the caller until the act is done. */
  idempotency_key: string;
}

/** What changes on a task: a field left out is kept; `due: null` removes the date. */
export interface TaskChangeBody {
  title?: string;
  notes?: string;
  due?: string | null;
  completed?: boolean;
}

type NewTaskRequest = NewTaskBody & { list_id: string };
type TaskChangeRequest = TaskChangeBody & { list_id: string; task_id: string };
interface NewListRequest {
  title: string;
  idempotency_key: string;
}

export interface WorkbenchTasksState {
  /** The open list: the one asked for, else the first; null while there is none. */
  listId: string | null;
  lists: WorkbenchPageState<WorkbenchTaskList>;
  tasks: WorkbenchPageState<WorkbenchTask>;
  /** Tasks whose completion is on its way (their checkbox takes no second one). */
  pending: ReadonlySet<string>;
  setCompleted: (task: WorkbenchTask, completed: boolean) => Promise<void>;
  saveTask: (task: WorkbenchTask, change: TaskChangeBody) => Promise<void>;
  addTask: (body: NewTaskBody) => Promise<void>;
  removeTask: (task: WorkbenchTask) => Promise<void>;
  addList: (title: string, idempotencyKey: string) => Promise<WorkbenchTaskList | undefined>;
  removeList: (list: WorkbenchTaskList) => Promise<void>;
}

/** The provider no longer has it: for a removal, that is the removal done. */
function isGone(error: unknown): boolean {
  return workbenchRefusal(error)?.key === 'workbench.errors.item_gone';
}

/** A second submission of one key: the first's outcome is told, the list re-read. */
function isReplay(error: unknown): boolean {
  return workbenchRefusal(error)?.key.startsWith('workbench.errors.already_submitted') ?? false;
}

/**
 * @param requested - The list the address names; null opens the first one.
 * @param showCompleted - Whether completed tasks are listed too.
 * @returns The open list, the two listings and the screen's acts.
 */
export function useWorkbenchTasks(
  requested: string | null,
  showCompleted: boolean
): WorkbenchTasksState {
  const lists = useWorkbenchPage<WorkbenchTaskList>(LISTS_PATH, NO_PARAMS);
  const listId = requested ?? lists.items[0]?.id ?? null;
  const tasks = useWorkbenchPage<WorkbenchTask>(listId ? TASKS_PATH : null, {
    list_id: listId ?? undefined,
    show_completed: showCompleted,
  });
  const { items: shownTasks, replaceItem: replaceTask, refresh: rereadTasks } = tasks;
  const { replaceItem: replaceList, refresh: rereadLists } = lists;
  const { mutate: postTask } = useApiMutation<NewTaskRequest, WorkbenchTask>({
    method: 'POST',
    componentName: 'WorkbenchTasks',
  });
  const { mutate: postList } = useApiMutation<NewListRequest, WorkbenchTaskList>({
    method: 'POST',
    componentName: 'WorkbenchTasks',
  });
  const { mutate: patchTask } = useApiMutation<TaskChangeRequest, WorkbenchTask>({
    method: 'PATCH',
    componentName: 'WorkbenchTasks',
  });
  const { mutate: remove } = useApiMutation<undefined, void>({
    method: 'DELETE',
    componentName: 'WorkbenchTasks',
  });
  // Set synchronously: a second click lands before the render that shows the first.
  const inFlight = useRef(new Set<string>());
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  const settle = useCallback((id: string, busy: boolean) => {
    if (busy) inFlight.current.add(id);
    else inFlight.current.delete(id);
    setPending(new Set(inFlight.current));
  }, []);

  const setCompleted = useCallback(
    async (task: WorkbenchTask, completed: boolean) => {
      if (!listId || inFlight.current.has(task.id)) return;
      settle(task.id, true);
      replaceTask(task.id, { ...task, completed });
      try {
        const saved = await patchTask(TASKS_PATH, { list_id: listId, task_id: task.id, completed });
        if (saved) replaceTask(task.id, saved);
      } catch (error: unknown) {
        replaceTask(task.id, task);
        throw error;
      } finally {
        settle(task.id, false);
      }
    },
    [listId, patchTask, replaceTask, settle]
  );

  const saveTask = useCallback(
    async (task: WorkbenchTask, change: TaskChangeBody) => {
      if (!listId) return;
      const saved = await patchTask(TASKS_PATH, { list_id: listId, task_id: task.id, ...change });
      if (saved) replaceTask(task.id, saved);
    },
    [listId, patchTask, replaceTask]
  );

  const addTask = useCallback(
    async (body: NewTaskBody) => {
      if (!listId) return;
      try {
        await postTask(TASKS_PATH, { list_id: listId, ...body });
      } catch (error: unknown) {
        if (isReplay(error)) void rereadTasks();
        throw error;
      }
      await rereadTasks();
    },
    [listId, postTask, rereadTasks]
  );

  const removeTask = useCallback(
    async (task: WorkbenchTask) => {
      if (!listId) return;
      const hadSubtasks = shownTasks.some(item => item.parent === task.id);
      try {
        await remove(TASKS_PATH, undefined, { params: { list_id: listId, task_id: task.id } });
      } catch (error: unknown) {
        if (!isGone(error)) throw error;
      }
      replaceTask(task.id, null);
      if (hadSubtasks) await rereadTasks();
    },
    [listId, remove, replaceTask, rereadTasks, shownTasks]
  );

  const addList = useCallback(
    async (title: string, idempotencyKey: string) => {
      try {
        const created = await postList(LISTS_PATH, { title, idempotency_key: idempotencyKey });
        await rereadLists();
        return created;
      } catch (error: unknown) {
        if (isReplay(error)) void rereadLists();
        throw error;
      }
    },
    [postList, rereadLists]
  );

  const removeList = useCallback(
    async (list: WorkbenchTaskList) => {
      try {
        await remove(LISTS_PATH, undefined, { params: { list_id: list.id } });
      } catch (error: unknown) {
        if (!isGone(error)) throw error;
      }
      replaceList(list.id, null);
    },
    [remove, replaceList]
  );

  return {
    listId,
    lists,
    tasks,
    pending,
    setCompleted,
    saveTask,
    addTask,
    removeTask,
    addList,
    removeList,
  };
}
