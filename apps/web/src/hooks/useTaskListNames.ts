'use client';

import { useCallback, useRef } from 'react';

import type { WorkbenchPage } from '@/hooks/useWorkbenchPage';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import type { WorkbenchTaskList } from '@/lib/workbench/types';

const LISTS_PATH = '/workbench/tasks/lists';

/**
 * The names of the person's task lists, read when a message is about to become a task (owner,
 * 2026-11-07): LIA reads the message against them and names the one it belongs to.
 *
 * Read on the first press, never on every message opened: listing them costs a provider call. The
 * names then serve the screen's later presses. A failed read leaves LIA without them, the task
 * landing in the list the form opens on, where the person can choose another: it never stops the
 * task, and it is asked again next time.
 *
 * @param offered - A tasks tool is ready: there is nowhere for a task to go otherwise.
 * @returns What reads the names, the first page of them.
 */
export function useTaskListNames(offered: boolean): () => Promise<string[]> {
  const known = useRef<string[] | null>(null);
  return useCallback(async () => {
    if (!offered) return [];
    if (known.current) return known.current;
    try {
      const page = await apiClient.get<WorkbenchPage<WorkbenchTaskList>>(LISTS_PATH);
      known.current = (page?.items ?? [])
        .map(list => list.title.trim())
        .filter(name => name !== '');
      return known.current;
    } catch (error: unknown) {
      logger.debug('task_list_names_unread', { error: String(error) });
      return [];
    }
  }, [offered]);
}
