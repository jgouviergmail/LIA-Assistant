/**
 * The tasks screen's model (ADR-369): pure, read by the screen and its rows.
 *
 * A subtask sits under its parent, in the parent's order; one whose parent is
 * not on screen yet (another page) keeps its own place rather than vanish. A
 * due day is told against the ACCOUNT's today — its zone, not the browser's —
 * and a count is exact or absent (ADR-185): what is left to do is counted
 * only when the whole list is on screen.
 */
import { getIntlLocale, type Language } from '@/i18n/settings';

import type { WorkbenchTask } from './types';

/** A top-level task and the subtasks under it. */
export interface TaskNode {
  task: WorkbenchTask;
  children: WorkbenchTask[];
}

/** How a due day reads against today. */
export type DueTone = 'overdue' | 'today' | 'later';

function bySiblingOrder(left: WorkbenchTask, right: WorkbenchTask): number {
  return (left.position ?? '').localeCompare(right.position ?? '');
}

/**
 * @param items - The tasks on screen, in the provider's order.
 * @returns The top-level tasks in that order, each with its subtasks under it.
 */
export function taskTree(items: readonly WorkbenchTask[]): TaskNode[] {
  const shown = new Set(items.map(item => item.id));
  const children = new Map<string, WorkbenchTask[]>();
  for (const item of items) {
    if (item.parent && shown.has(item.parent)) {
      children.set(item.parent, [...(children.get(item.parent) ?? []), item]);
    }
  }
  return items
    .filter(item => !item.parent || !shown.has(item.parent))
    .map(item => ({
      task: item,
      children: [...(children.get(item.id) ?? [])].sort(bySiblingOrder),
    }));
}

/**
 * Today, as a `YYYY-MM-DD` day in the account's zone.
 *
 * @param zone - The account's IANA zone; missing or unknown → the browser's.
 * @param now - The instant to read.
 * @returns The day.
 */
export function dayIn(zone: string | undefined, now: Date): string {
  const options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  };
  try {
    return new Intl.DateTimeFormat('en-CA', { ...options, timeZone: zone }).format(now);
  } catch {
    // An unknown zone (RangeError): the browser's own day is the honest fallback.
    return new Intl.DateTimeFormat('en-CA', options).format(now);
  }
}

/**
 * @param task - A task.
 * @param today - Today in the account's zone (`dayIn`).
 * @returns How its due day reads; a done task is never late; null without a day.
 */
export function dueTone(task: WorkbenchTask, today: string): DueTone | null {
  if (!task.due) return null;
  if (task.completed || task.due > today) return 'later';
  return task.due === today ? 'today' : 'overdue';
}

/**
 * @param items - The tasks on screen.
 * @param nextToken - The listing's next page token (null on the last page).
 * @returns What is left to do, or null while part of the list is not read.
 */
export function openCount(
  items: readonly WorkbenchTask[],
  nextToken: string | null
): number | null {
  return nextToken === null ? items.filter(item => !item.completed).length : null;
}

/** A `YYYY-MM-DD` day in the reader's language (« jeu. 5 nov. »), never shifted by a zone. */
export function formatDay(day: string, lng: Language): string {
  const [year, month, date] = day.split('-').map(Number);
  if (!year || !month || !date) return day;
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, date)));
}
