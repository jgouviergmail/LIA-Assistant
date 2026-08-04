/**
 * scheduleShape — the schedule-synthesis classifier (layout program).
 */

import { describe, it, expect } from 'vitest';

import { scheduleShape } from '../schedule-label';

describe('scheduleShape', () => {
  it('names the three common shapes', () => {
    expect(scheduleShape([1, 2, 3, 4, 5, 6, 7])).toBe('daily');
    expect(scheduleShape([1, 2, 3, 4, 5])).toBe('weekdays');
    expect(scheduleShape([6, 7])).toBe('weekend');
  });

  it('is order- and duplicate-tolerant', () => {
    expect(scheduleShape([5, 3, 1, 4, 2])).toBe('weekdays');
    expect(scheduleShape([7, 6, 7])).toBe('weekend');
  });

  it('falls back to custom for anything irregular', () => {
    expect(scheduleShape([])).toBe('custom');
    expect(scheduleShape([1])).toBe('custom');
    expect(scheduleShape([1, 2, 3, 4])).toBe('custom');
    expect(scheduleShape([1, 2, 3, 4, 5, 6])).toBe('custom');
    expect(scheduleShape([2, 3, 4, 5, 6])).toBe('custom');
  });
});
