/**
 * Where the week grid draws each event (ADR-369, Task 5.2).
 *
 * Events that overlap sit side by side, each cluster as wide as it needs and
 * no wider; past the column budget the rest is counted (« +N »), never drawn
 * on top of each other. A timed event that spans midnight is drawn on each day
 * it touches; an all-day event is a bar across its days, its end exclusive.
 */

import { describe, expect, it } from 'vitest';

import { daySegments, eventDays, layoutAllDay, layoutDay, monthGrid } from '../layout';

const PARIS = 'Europe/Paris';

describe('layoutDay', () => {
  it('puts events that overlap side by side and leaves a lone one whole', () => {
    const layout = layoutDay([
      { id: 'a', start: 600, end: 660 },
      { id: 'b', start: 630, end: 720 },
      { id: 'c', start: 900, end: 960 },
    ]);

    const placed = Object.fromEntries(layout.placed.map(event => [event.id, event]));
    expect([placed.a.column, placed.a.columns]).toEqual([0, 2]);
    expect([placed.b.column, placed.b.columns]).toEqual([1, 2]);
    expect([placed.c.column, placed.c.columns]).toEqual([0, 1]);
    expect(layout.more).toEqual([]);
  });

  it('reuses a column freed earlier in the same cluster', () => {
    const layout = layoutDay([
      { id: 'a', start: 600, end: 720 },
      { id: 'b', start: 600, end: 630 },
      { id: 'c', start: 640, end: 700 },
    ]);

    const placed = Object.fromEntries(layout.placed.map(event => [event.id, event]));
    expect(placed.c.column).toBe(placed.b.column);
    expect(placed.a.columns).toBe(2);
  });

  it('counts what passes the column budget instead of drawing it on top', () => {
    const many = Array.from({ length: 5 }, (_, index) => ({
      id: `e${index}`,
      start: 600,
      end: 660,
    }));

    const layout = layoutDay(many, 3);

    expect(layout.placed.map(event => event.id)).toEqual(['e0', 'e1']);
    expect(layout.placed.every(event => event.columns === 3)).toBe(true);
    expect(layout.more).toEqual([
      { start: 600, end: 660, column: 2, columns: 3, ids: ['e2', 'e3', 'e4'] },
    ]);
  });

  it('gives a very short event room enough to be read before judging overlaps', () => {
    const layout = layoutDay([
      { id: 'a', start: 600, end: 605 },
      { id: 'b', start: 610, end: 670 },
    ]);

    expect(layout.placed.every(event => event.columns === 2)).toBe(true);
  });
});

describe('daySegments', () => {
  const days = ['2026-11-02', '2026-11-03', '2026-11-04'];

  it('draws a timed event that crosses midnight on each day it touches', () => {
    const segments = daySegments('2026-11-02T21:00:00Z', '2026-11-03T08:30:00Z', days, PARIS);

    expect(segments).toEqual({
      '2026-11-02': { start: 22 * 60, end: 24 * 60, continues: true, continued: false },
      '2026-11-03': { start: 0, end: 9 * 60 + 30, continues: false, continued: true },
    });
  });

  it('draws nothing for a day the event does not touch, an end at midnight included', () => {
    const segments = daySegments('2026-11-03T08:00:00Z', '2026-11-03T23:00:00Z', days, PARIS);

    expect(Object.keys(segments)).toEqual(['2026-11-03']);
    expect(segments['2026-11-03'].end).toBe(24 * 60);
  });
});

describe('layoutAllDay', () => {
  const days = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05'];

  it('draws a bar across its days, the end exclusive, cut at the view’s edges', () => {
    const layout = layoutAllDay(
      [
        { id: 'trip', start: '2026-11-03', end: '2026-11-05' },
        { id: 'long', start: '2026-10-30', end: '2026-11-10' },
      ],
      days,
      3
    );

    const placed = Object.fromEntries(layout.placed.map(bar => [bar.id, bar]));
    expect([placed.trip.first, placed.trip.last]).toEqual([1, 2]);
    expect([placed.long.first, placed.long.last]).toEqual([0, 3]);
    expect(placed.trip.lane).not.toBe(placed.long.lane);
  });

  it('counts per day what passes the lane budget', () => {
    const bars = Array.from({ length: 4 }, (_, index) => ({
      id: `b${index}`,
      start: '2026-11-02',
      end: '2026-11-03',
    }));

    const layout = layoutAllDay(bars, days, 2);

    expect(layout.placed.map(bar => bar.id)).toEqual(['b0']);
    expect(layout.more).toEqual({ 0: ['b1', 'b2', 'b3'] });
  });
});

describe('monthGrid', () => {
  it('is six weeks from the first weekday of the week holding the first of the month', () => {
    const grid = monthGrid('2026-10-28', 1);

    expect(grid).toHaveLength(42);
    expect([grid[0], grid[41]]).toEqual(['2026-09-28', '2026-11-08']);
  });

  it('starts on Sunday where the locale’s week does', () => {
    expect(monthGrid('2026-11-15', 7)[0]).toBe('2026-11-01');
  });
});

describe('eventDays', () => {
  it('is an all-day event’s own days, the end exclusive', () => {
    expect(eventDays({ all_day: true, start: '2026-11-02', end: '2026-11-05' }, PARIS)).toEqual({
      start: '2026-11-02',
      end: '2026-11-05',
    });
  });

  it('is every day a timed event touches on the account’s wall, an end at midnight excluded', () => {
    expect(
      eventDays(
        { all_day: false, start: '2026-11-02T21:00:00Z', end: '2026-11-03T08:30:00Z' },
        PARIS
      )
    ).toEqual({ start: '2026-11-02', end: '2026-11-04' });
    expect(
      eventDays(
        { all_day: false, start: '2026-11-03T08:00:00Z', end: '2026-11-03T23:00:00Z' },
        PARIS
      )
    ).toEqual({ start: '2026-11-03', end: '2026-11-04' });
  });
});
