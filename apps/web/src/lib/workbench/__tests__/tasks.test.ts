/**
 * The tasks screen's model (ADR-369): subtasks sit under their parent, a due
 * day is told against the account's own today, and a count is exact or absent.
 */

import { describe, expect, it } from 'vitest';

import type { WorkbenchTask } from '../types';
import { dayIn, dueTone, openCount, taskTree } from '../tasks';

function task(id: string, overrides: Partial<WorkbenchTask> = {}): WorkbenchTask {
  return {
    id,
    title: id,
    notes: null,
    completed: false,
    due: null,
    parent: null,
    position: null,
    ...overrides,
  };
}

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
});

describe('openCount', () => {
  it('counts what is left to do only when the whole list is on screen', () => {
    const items = [task('a'), task('b', { completed: true }), task('c')];
    expect(openCount(items, null)).toBe(2);
    expect(openCount(items, 'next-page')).toBeNull();
  });
});
