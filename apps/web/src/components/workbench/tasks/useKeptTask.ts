'use client';

/**
 * A task the address names that the list's pages read do not hold (owner, 2026-11-07).
 *
 * The home opens a task in its own list, and that task may sit past the first page. It is read
 * alone (`GET /workbench/tasks/task`) and kept at the head of the list, so every act of the screen
 * reaches it as it reaches any other; a task that is gone is said, and nothing opens. Nothing is
 * read while the list is, nor for a list that failed (its own refusal is said).
 */
import { useEffect } from 'react';

import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import type { WorkbenchPageState } from '@/hooks/useWorkbenchPage';
import type { WorkbenchTask } from '@/lib/workbench/types';

const ONE_TASK_PATH = '/workbench/tasks/task';

/**
 * @param taskId - The task the address names, if any.
 * @param listId - The open list.
 * @param tasks - The open list's tasks, as read.
 * @param tell - Says a refusal.
 */
export function useKeptTask(
  taskId: string | null,
  listId: string | null,
  tasks: WorkbenchPageState<WorkbenchTask>,
  tell: (error: unknown) => void
): void {
  const missing =
    taskId !== null &&
    listId !== null &&
    !tasks.loading &&
    tasks.error === null &&
    !tasks.items.some(item => item.id === taskId);
  const alone = useWorkbenchItem<WorkbenchTask>(missing ? ONE_TASK_PATH : null, {
    list_id: listId ?? undefined,
    task_id: taskId ?? undefined,
  });
  const { keepItem } = tasks;
  useEffect(() => {
    if (missing && alone.item) keepItem(alone.item);
  }, [missing, alone.item, keepItem]);
  useEffect(() => {
    if (missing && alone.error) tell(alone.error);
  }, [missing, alone.error, tell]);
}
