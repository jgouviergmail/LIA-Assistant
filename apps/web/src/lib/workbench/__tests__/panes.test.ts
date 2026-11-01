/**
 * The « Tools » panes a person sizes by hand: each declares its bounds, and the
 * panes beside it always keep room — on a wide screen the declared maximum
 * holds, on a narrow one the pane takes no more than its share of the row.
 */

import { describe, expect, it } from 'vitest';

import { WORKBENCH_PANES, isWorkbenchPane, paneBounds, type WorkbenchPane } from '../panes';

const PANES = Object.entries(WORKBENCH_PANES) as [
  WorkbenchPane,
  (typeof WORKBENCH_PANES)[WorkbenchPane],
][];

describe('WORKBENCH_PANES', () => {
  it.each(PANES)('%s starts inside its own bounds and leaves its row room', (_pane, spec) => {
    expect(spec.min).toBeLessThanOrEqual(spec.initial);
    expect(spec.initial).toBeLessThanOrEqual(spec.max);
    expect(spec.share).toBeGreaterThan(0);
    expect(spec.share).toBeLessThan(1);
    expect(spec.labelKey).toMatch(/^workbench\.panes\./);
  });

  it('leaves the tool’s own pane room where two panes share one row', () => {
    // Mail: folders + list beside the reader; calendar: calendars + detail
    // beside the view; tasks: lists + detail beside the tasks.
    for (const [left, right] of [
      ['mail.folders', 'mail.list'],
      ['calendar.calendars', 'calendar.detail'],
      ['tasks.lists', 'tasks.editor'],
    ] as const) {
      // The third pane (the reader, the view, the tasks) keeps at least 30 %.
      expect(WORKBENCH_PANES[left].share + WORKBENCH_PANES[right].share).toBeLessThanOrEqual(0.7);
    }
  });
});

describe('paneBounds', () => {
  const spec = WORKBENCH_PANES['contacts.list'];

  it('holds the declared maximum on a wide row', () => {
    expect(paneBounds(spec, 2000)).toEqual({ min: spec.min, max: spec.max });
  });

  it('takes no more than its share of a narrow row', () => {
    expect(paneBounds(spec, 1000)).toEqual({ min: spec.min, max: Math.floor(1000 * spec.share) });
  });

  it('never offers less than its minimum, measured or not', () => {
    expect(paneBounds(spec, 300)).toEqual({ min: spec.min, max: spec.min });
    expect(paneBounds(spec, 0)).toEqual({ min: spec.min, max: spec.min });
  });
});

describe('isWorkbenchPane', () => {
  it('knows the declared panes and nothing else', () => {
    expect(isWorkbenchPane('mail.folders')).toBe(true);
    expect(isWorkbenchPane('mail.reader')).toBe(false);
    expect(isWorkbenchPane('constructor')).toBe(false);
  });
});
