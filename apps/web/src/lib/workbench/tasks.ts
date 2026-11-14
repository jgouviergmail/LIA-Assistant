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

import { instantToWall, wallTimeToInstant } from './calendar/zoned';
import type { ViewTask, WorkbenchTask, WorkbenchTaskView } from './types';

/** A top-level task and the subtasks under it. */
export interface TaskNode {
  task: WorkbenchTask;
  children: WorkbenchTask[];
}

/** How a due day reads against today. */
export type DueTone = 'overdue' | 'today' | 'later';

/** The views across the lists, in the pane's order: the three together first. */
export const TASK_VIEWS: readonly WorkbenchTaskView[] = [
  'timeline',
  'today',
  'overdue',
  'upcoming',
];

/** Every open task of every list: a view too, which the pane draws among the lists. */
export const ALL_TASKS_VIEW = 'all' satisfies WorkbenchTaskView;

/** Every view the address or the phone's select may name. */
export const NAMED_TASK_VIEWS: readonly WorkbenchTaskView[] = [...TASK_VIEWS, ALL_TASKS_VIEW];

/** What the address names, when it is a view. */
export function taskView(raw: string | null): WorkbenchTaskView | null {
  return NAMED_TASK_VIEWS.find(view => view === raw) ?? null;
}

/** The stretches of the timeline, in time order. */
const TIMELINE_PARTS = ['overdue', 'today', 'upcoming'] as const;

/** One stretch of the timeline, named as the view that shows it alone. */
export type TimelinePart = (typeof TIMELINE_PARTS)[number];

/** A stretch of the timeline and the tasks that fall in it. */
export interface TimelineSection {
  part: TimelinePart;
  tasks: ViewTask[];
}

function timelinePart(due: string, today: string): TimelinePart {
  if (due < today) return 'overdue';
  return due === today ? 'today' : 'upcoming';
}

/**
 * @param tasks - What the timeline gathers, in the server's order.
 * @param today - Today in the account's zone (`dayIn`).
 * @returns Its stretches that hold something, in time order, each task once.
 */
export function timelineSections(tasks: readonly ViewTask[], today: string): TimelineSection[] {
  return TIMELINE_PARTS.map(part => ({
    part,
    tasks: tasks.filter(task => task.due !== null && timelinePart(task.due, today) === part),
  })).filter(section => section.tasks.length > 0);
}

/** The tasks a task sits among: its parent's, or the top level. */
export function siblingsOf(items: readonly WorkbenchTask[], task: WorkbenchTask): WorkbenchTask[] {
  return items.filter(item => (item.parent ?? null) === (task.parent ?? null));
}

/**
 * @param siblings - The tasks it sits among, in their order.
 * @param id - The task.
 * @param by - One place up (-1) or down (1).
 * @returns The sibling it would follow (null: first), or null when it has nowhere to go.
 */
export function placementOf(
  siblings: readonly WorkbenchTask[],
  id: string,
  by: -1 | 1
): { after: string | null } | null {
  const at = siblings.findIndex(item => item.id === id);
  const target = at + by;
  if (at < 0 || target < 0 || target >= siblings.length) return null;
  const follows = by < 0 ? siblings[at - 2] : siblings[at + 1];
  return { after: follows?.id ?? null };
}

/** A reminder as a `datetime-local` field holds it, on the account's clock. */
export function reminderInput(reminder: string | null, zone: string): string {
  if (!reminder) return '';
  const wall = instantToWall(new Date(reminder), zone);
  return `${wall.date}T${wall.time}`;
}

/** What a `datetime-local` field names on the account's clock, as an instant. */
export function reminderInstant(field: string, zone: string): string | null {
  if (!field) return null;
  const [date, time] = field.split('T');
  return wallTimeToInstant(date, time, zone).toISOString();
}

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
export function dueTone(
  task: Pick<WorkbenchTask, 'due' | 'completed'>,
  today: string
): DueTone | null {
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
