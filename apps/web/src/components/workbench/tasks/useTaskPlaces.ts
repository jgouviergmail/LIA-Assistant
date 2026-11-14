'use client';

/**
 * Where the tasks screen stands, on the address (ADR-369).
 *
 * The list or the view on screen (`?list=`, `?view=`) and the open task (`?task=`) ride the
 * address. A view stands in the place of a list; a task opened from a view opens BESIDE it —
 * the address keeps the view and names the task's own list, which is then read under the view
 * for the detail's sake (owner, 2026-11-10). Opening a task PUSHES (a link the browser
 * follows); every other move REPLACES, so « back » closes a detail rather than leave the screen.
 *
 * An address that names nothing opens on « All tasks » (owner, 2026-11-10): the default list
 * is where a new task goes, not where the screen starts. A task named without its list is the
 * one case still looked for in the default list, since nothing says where else it lives.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback } from 'react';

import type { Language } from '@/i18n/settings';
import { ALL_TASKS_VIEW, taskView } from '@/lib/workbench/tasks';
import { toolPath } from '@/lib/workbench/tools';
import type { WorkbenchTaskView } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

export interface TaskPlaces {
  /** The view on screen, in the place of a list: the one named, or « All tasks » with nothing named. */
  view: WorkbenchTaskView | null;
  /** The list the address names; null is the default one, read only for a task named alone. */
  requestedList: string | null;
  /** The task the address names, open in its detail. */
  openTaskId: string | null;
  /** Whether a list's tasks are read: not under a view, unless a task is open beside it. */
  readsList: boolean;
  /** The address of a place of the screen. */
  hrefOf: (query: Record<string, string>) => string;
  /** Goes to a place, in the place of the one on screen. */
  go: (query: Record<string, string>) => void;
}

/**
 * @param lng - The page's language.
 * @returns What the address names, and the two ways to another place.
 */
export function useTaskPlaces(lng: Language): TaskPlaces {
  const router = useRouter();
  const params = useSearchParams();
  const requestedList = params.get('list');
  const openTaskId = params.get('task');
  const nothingNamed = requestedList === null && openTaskId === null;
  const view = taskView(params.get('view')) ?? (nothingNamed ? ALL_TASKS_VIEW : null);
  const hrefOf = useCallback(
    (query: Record<string, string>) => {
      const search = new URLSearchParams(query).toString();
      return `${buildLocalizedPath(toolPath('tasks'), lng)}${search ? `?${search}` : ''}`;
    },
    [lng]
  );
  const go = useCallback(
    (query: Record<string, string>) => router.replace(hrefOf(query), { scroll: false }),
    [router, hrefOf]
  );
  return {
    view,
    requestedList,
    openTaskId,
    readsList: view === null || openTaskId !== null,
    hrefOf,
    go,
  };
}
