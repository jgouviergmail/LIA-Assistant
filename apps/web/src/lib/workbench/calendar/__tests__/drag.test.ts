/**
 * Where a dragged event lands (ADR-369, lot 2): pixels and a day become wall times.
 *
 * A move keeps the event's length and never leaves the day it was dropped on; a
 * resize keeps the start and leaves the event at least one step long. A drop
 * that changes nothing is no act.
 */
import { describe, expect, it } from 'vitest';

import { droppedFields, snappedMinutes, wallFieldsOf } from '../drag';
import { newEventFields } from '../editor';

const MORNING = newEventFields('primary', '2026-11-02', '09:00');

describe('snappedMinutes', () => {
  it('rounds a drag to the nearest quarter of an hour', () => {
    expect(snappedMinutes(0, 48)).toBe(0);
    expect(snappedMinutes(5, 48)).toBe(0);
    expect(snappedMinutes(7, 48)).toBe(15);
    expect(snappedMinutes(48, 48)).toBe(60);
    expect(snappedMinutes(-49, 48)).toBe(-60);
  });
});

describe('droppedFields — a move', () => {
  it('moves the bounds together, on the day under the pointer', () => {
    const moved = droppedFields(MORNING, { edge: 'move', minutes: 90, day: '2026-11-04' });
    expect(moved).toMatchObject({
      startDate: '2026-11-04',
      startTime: '10:30',
      endDate: '2026-11-04',
      endTime: '11:30',
    });
  });

  it('stays on the day it was dropped on, at the top and at the bottom', () => {
    const early = droppedFields(MORNING, { edge: 'move', minutes: -600, day: '2026-11-02' });
    expect(early).toMatchObject({ startTime: '00:00', endTime: '01:00' });
    const late = droppedFields(MORNING, { edge: 'move', minutes: 900, day: '2026-11-02' });
    expect(late).toMatchObject({
      startDate: '2026-11-02',
      startTime: '23:00',
      endDate: '2026-11-03',
      endTime: '00:00',
    });
  });

  it('is no act when it lands where it was', () => {
    expect(droppedFields(MORNING, { edge: 'move', minutes: 0, day: '2026-11-02' })).toBeNull();
  });
});

describe('droppedFields — a resize', () => {
  it('moves the end alone', () => {
    const longer = droppedFields(MORNING, { edge: 'end', minutes: 45, day: '2026-11-02' });
    expect(longer).toMatchObject({ startTime: '09:00', endTime: '10:45' });
  });

  it('keeps one step of length, and ends at midnight at the latest', () => {
    const short = droppedFields(MORNING, { edge: 'end', minutes: -120, day: '2026-11-02' });
    expect(short).toMatchObject({ startTime: '09:00', endTime: '09:15' });
    const long = droppedFields(MORNING, { edge: 'end', minutes: 2000, day: '2026-11-02' });
    expect(long).toMatchObject({ endDate: '2026-11-03', endTime: '00:00' });
  });

  it('ignores the day under the pointer', () => {
    const longer = droppedFields(MORNING, { edge: 'end', minutes: 15, day: '2026-11-05' });
    expect(longer).toMatchObject({ startDate: '2026-11-02', endDate: '2026-11-02' });
  });
});

describe('wallFieldsOf', () => {
  it('reads an event on the account’s wall, across a clock change', () => {
    const fields = wallFieldsOf(
      { start: '2026-10-25T00:30:00Z', end: '2026-10-25T02:30:00Z' },
      'Europe/Paris'
    );
    expect(fields).toEqual({
      startDate: '2026-10-25',
      startTime: '02:30',
      endDate: '2026-10-25',
      endTime: '03:30',
    });
  });
});
