/**
 * The tasks screen's model (ADR-369): subtasks sit under their parent, a due
 * day is told against the account's own today, and a count is exact or absent.
 */

import { describe, expect, it } from 'vitest';

import type { ViewTask, WorkbenchTask } from '../types';
import {
  ALL_TASKS_VIEW,
  NAMED_TASK_VIEWS,
  TASK_VIEWS,
  dayIn,
  dueTone,
  openCount,
  placementOf,
  reminderInput,
  reminderInstant,
  siblingsOf,
  taskTree,
  taskView,
  timelineSections,
} from '../tasks';

function task(id: string, overrides: Partial<WorkbenchTask> = {}): WorkbenchTask {
  return {
    id,
    title: id,
    notes: null,
    completed: false,
    due: null,
    parent: null,
    position: null,
    steps: [],
    importance: null,
    reminder: null,
    repeat: null,
    ...overrides,
  };
}

describe('placementOf', () => {
  const siblings = [task('a'), task('b'), task('c')];

  it('moves a task up behind the one before its neighbour', () => {
    expect(placementOf(siblings, 'c', -1)).toEqual({ after: 'a' });
  });

  it('moves the second task to the top', () => {
    expect(placementOf(siblings, 'b', -1)).toEqual({ after: null });
  });

  it('moves a task down behind its neighbour', () => {
    expect(placementOf(siblings, 'a', 1)).toEqual({ after: 'b' });
  });

  it('has nowhere to go past either end', () => {
    expect(placementOf(siblings, 'a', -1)).toBeNull();
    expect(placementOf(siblings, 'c', 1)).toBeNull();
  });

  it('knows nothing of a task it does not hold', () => {
    expect(placementOf(siblings, 'z', 1)).toBeNull();
  });
});

describe('siblingsOf', () => {
  const items = [task('a'), task('b', { parent: 'a' }), task('c'), task('d', { parent: 'a' })];

  it('reads the top level for a top-level task', () => {
    expect(siblingsOf(items, items[0]).map(item => item.id)).toEqual(['a', 'c']);
  });

  it('reads the task under one parent for a subtask', () => {
    expect(siblingsOf(items, items[1]).map(item => item.id)).toEqual(['b', 'd']);
  });
});

describe('taskView', () => {
  it('reads the three views', () => {
    expect(taskView('today')).toBe('today');
    expect(taskView('overdue')).toBe('overdue');
    expect(taskView('upcoming')).toBe('upcoming');
  });

  it('reads anything else as no view', () => {
    expect(taskView('someday')).toBeNull();
    expect(taskView(null)).toBeNull();
  });

  it('knows the three together and every open task too', () => {
    expect(taskView('timeline')).toBe('timeline');
    expect(taskView('all')).toBe('all');
  });

  it('keeps « all tasks » out of the views group, which the three together head', () => {
    expect(TASK_VIEWS).toEqual(['timeline', 'today', 'overdue', 'upcoming']);
    expect(TASK_VIEWS).not.toContain(ALL_TASKS_VIEW);
    expect(NAMED_TASK_VIEWS).toEqual([...TASK_VIEWS, ALL_TASKS_VIEW]);
  });
});

describe('timelineSections', () => {
  const TODAY = '2026-11-10';
  const due = (id: string, day: string | null): ViewTask => ({
    id,
    list_id: 'l1',
    title: id,
    due: day,
  });

  it('cuts what the timeline gathers into what is late, today and the days ahead', () => {
    const tasks = [
      due('old', '2019-01-01'),
      due('yesterday', '2026-11-09'),
      due('now', '2026-11-10'),
      due('tomorrow', '2026-11-11'),
      due('later', '2026-11-17'),
    ];

    const sections = timelineSections(tasks, TODAY);

    expect(sections.map(section => [section.part, section.tasks.map(task => task.id)])).toEqual([
      ['overdue', ['old', 'yesterday']],
      ['today', ['now']],
      ['upcoming', ['tomorrow', 'later']],
    ]);
  });

  it('draws no stretch that holds nothing', () => {
    expect(timelineSections([due('now', TODAY)], TODAY).map(section => section.part)).toEqual([
      'today',
    ]);
    expect(timelineSections([], TODAY)).toEqual([]);
  });

  it('places every dated task once, and never one without a day', () => {
    const tasks = [due('a', '2026-11-09'), due('b', TODAY), due('c', '2026-11-12'), due('d', null)];

    const placed = timelineSections(tasks, TODAY).flatMap(section => section.tasks);

    expect(placed.map(task => task.id)).toEqual(['a', 'b', 'c']);
  });
});

describe('reminderInput', () => {
  it("shows an instant on the account's clock", () => {
    expect(reminderInput('2027-01-10T09:00:00Z', 'Europe/Paris')).toBe('2027-01-10T10:00');
  });

  it('shows nothing without a reminder', () => {
    expect(reminderInput(null, 'Europe/Paris')).toBe('');
  });

  it('writes what the field holds as the instant it names there', () => {
    expect(reminderInstant('2027-01-10T10:00', 'Europe/Paris')).toBe('2027-01-10T09:00:00.000Z');
  });

  it('writes nothing for an empty field', () => {
    expect(reminderInstant('', 'Europe/Paris')).toBeNull();
  });

  it('gives back what it reads', () => {
    const shown = reminderInput('2027-07-01T06:30:00Z', 'America/New_York');

    expect(reminderInstant(shown, 'America/New_York')).toBe('2027-07-01T06:30:00.000Z');
  });
});

describe('taskTree', () => {
  it('puts each subtask under its parent, in the parent’s order', () => {
    const tree = taskTree([
      task('a'),
      task('a2', { parent: 'a', position: '2' }),
      task('b'),
      task('a1', { parent: 'a', position: '1' }),
    ]);

    expect(tree.map(node => [node.task.id, node.children.map(child => child.id)])).toEqual([
      ['a', ['a1', 'a2']],
      ['b', []],
    ]);
  });

  it('keeps a subtask whose parent is not on screen yet, at its own place', () => {
    const tree = taskTree([task('a'), task('orphan', { parent: 'elsewhere' })]);
    expect(tree.map(node => node.task.id)).toEqual(['a', 'orphan']);
  });
});

describe('dayIn', () => {
  it('reads today in the account’s zone, not the browser’s', () => {
    const lateEvening = new Date('2026-11-03T23:30:00Z');
    expect(dayIn('Europe/Paris', lateEvening)).toBe('2026-11-04');
    expect(dayIn('America/New_York', lateEvening)).toBe('2026-11-03');
  });

  it('falls back on the browser’s zone when the account names none or an unknown one', () => {
    const noon = new Date('2026-11-03T12:00:00Z');
    expect(dayIn(undefined, noon)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(dayIn('Mars/Olympus', noon)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('dueTone', () => {
  it('tells a day past, today and to come — and nothing for a done task', () => {
    expect(dueTone(task('t', { due: '2026-11-02' }), '2026-11-03')).toBe('overdue');
    expect(dueTone(task('t', { due: '2026-11-03' }), '2026-11-03')).toBe('today');
    expect(dueTone(task('t', { due: '2026-11-04' }), '2026-11-03')).toBe('later');
    expect(dueTone(task('t', { due: '2026-11-02', completed: true }), '2026-11-03')).toBe('later');
    expect(dueTone(task('t'), '2026-11-03')).toBeNull();
  });

  it('reads a row of a view, which holds a day and is never done', () => {
    expect(dueTone({ due: '2026-11-02', completed: false }, '2026-11-03')).toBe('overdue');
    expect(dueTone({ due: '2026-11-03', completed: false }, '2026-11-03')).toBe('today');
  });
});

describe('openCount', () => {
  it('counts what is left to do only when the whole list is on screen', () => {
    const items = [task('a'), task('b', { completed: true }), task('c')];
    expect(openCount(items, null)).toBe(2);
    expect(openCount(items, 'next-page')).toBeNull();
  });
});
