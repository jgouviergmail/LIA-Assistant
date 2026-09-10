/**
 * The recurrence helpers: pure, domain-free, and never the authority on a
 * schedule the server already computed.
 */

import { describe, it, expect } from 'vitest';

import type { DailyTimes, RecurrenceSpec } from '@/hooks/useScheduledActions';
import {
  clockLabel,
  emptyRecurrence,
  materialisedTimes,
  namedDaySet,
  recurrenceIsComplete,
  runsPerDay,
  WEEKDAY_SETS,
  withFreq,
} from '@/lib/recurrence';

const at = (...pairs: [number, number][]): DailyTimes => ({
  mode: 'at',
  at: pairs.map(([hour, minute]) => ({ hour, minute })),
});

describe('named day sets', () => {
  it('recognises the three shapes people actually schedule', () => {
    expect(namedDaySet(WEEKDAY_SETS.all)).toBe('all');
    expect(namedDaySet(WEEKDAY_SETS.workdays)).toBe('workdays');
    expect(namedDaySet(WEEKDAY_SETS.weekend)).toBe('weekend');
  });

  it('returns null for a genuinely irregular pick', () => {
    expect(namedDaySet([1, 3, 5])).toBeNull();
  });

  it('ignores order and duplicates', () => {
    expect(namedDaySet([7, 6, 6])).toBe('weekend');
  });
});

describe('materialised times (preview only)', () => {
  it('expands a step between its bounds', () => {
    const times: DailyTimes = {
      mode: 'every',
      step_minutes: 120,
      start: { hour: 8, minute: 0 },
      end: { hour: 14, minute: 0 },
    };
    expect(materialisedTimes(times).map(clockLabel)).toEqual([
      '08:00',
      '10:00',
      '12:00',
      '14:00',
    ]);
  });

  it('sorts and de-duplicates explicit moments', () => {
    expect(materialisedTimes(at([19, 0], [8, 0], [8, 0])).map(clockLabel)).toEqual([
      '08:00',
      '19:00',
    ]);
  });

  it('counts what a served day fires', () => {
    expect(runsPerDay(at([8, 0], [12, 30], [19, 0]))).toBe(3);
  });

  it('never loops forever on a degenerate step', () => {
    const times: DailyTimes = {
      mode: 'every',
      step_minutes: 0,
      start: { hour: 0, minute: 0 },
      end: { hour: 23, minute: 59 },
    };
    expect(materialisedTimes(times).length).toBeLessThanOrEqual(48);
  });
});

describe('switching frequency', () => {
  it('keeps the weekdays when moving between weekly shapes', () => {
    const weekly: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'weekly',
      byweekday: [1, 3],
    };
    expect(withFreq(weekly, 'weekly').byweekday).toEqual([1, 3]);
  });

  it('gives a monthly rule a day of month rather than leaving it empty', () => {
    const spec = withFreq(emptyRecurrence('2026-09-07'), 'monthly');
    expect(spec.bymonthday.length).toBeGreaterThan(0);
  });

  it('gives a weekly rule at least one weekday', () => {
    const spec = withFreq(emptyRecurrence('2026-09-07'), 'weekly');
    expect(spec.byweekday.length).toBeGreaterThan(0);
  });

  it('leaves behind no selector the new frequency cannot read', () => {
    // The API refuses a stored value its engine would ignore, so a residue
    // left here becomes a validation error the reader never caused. The
    // sequence is ordinary: pick weekly, tick Monday and Tuesday, change
    // your mind, pick daily.
    const weekly: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'weekly',
      byweekday: [1, 2],
    };
    expect(withFreq(weekly, 'daily').byweekday).toEqual([]);
    expect(withFreq(weekly, 'once').byweekday).toEqual([]);

    const yearly: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'yearly',
      bymonth: [1, 7],
      bymonthday: [15],
    };
    expect(withFreq(yearly, 'monthly').bymonth).toEqual([]);
    expect(withFreq(yearly, 'weekly').bymonth).toEqual([]);
    expect(withFreq(yearly, 'weekly').bymonthday).toEqual([]);

    const nth: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'monthly',
      nth_weekday: [2, 2],
      bymonthday: [],
    };
    expect(withFreq(nth, 'daily').nth_weekday).toBeNull();
    expect(withFreq(nth, 'yearly').nth_weekday).toBeNull();
  });

  it('still gives every frequency the selector it does read', () => {
    const weekly = withFreq(emptyRecurrence('2026-09-07'), 'weekly');
    expect(weekly.byweekday.length).toBeGreaterThan(0);
    const monthly = withFreq(weekly, 'monthly');
    expect(monthly.bymonthday.length).toBeGreaterThan(0);
    const yearly = withFreq(monthly, 'yearly');
    expect(yearly.bymonth.length).toBeGreaterThan(0);
    expect(yearly.bymonthday.length).toBeGreaterThan(0);
  });

  it('drops the end rule when moving to a single occurrence', () => {
    const repeating: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      end: { kind: 'after_count', on_date: null, after_count: 5 },
    };
    expect(withFreq(repeating, 'once').end.kind).toBe('never');
    expect(withFreq(repeating, 'once').interval).toBe(1);
  });
});

describe('completeness', () => {
  it('refuses a weekly rule with no weekday, as the API would', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      freq: 'weekly',
      byweekday: [],
    };
    expect(recurrenceIsComplete(spec)).toBe(false);
  });

  it('refuses a day with no moment', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-07'),
      times: { mode: 'at', at: [] },
    };
    expect(recurrenceIsComplete(spec)).toBe(false);
  });

  it('accepts the default a reader starts from', () => {
    expect(recurrenceIsComplete(emptyRecurrence('2026-09-07'))).toBe(true);
  });

  it('refuses an end date that precedes the anchor, as the API now would', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-10'),
      end: { kind: 'on_date', on_date: '2026-09-01', after_count: null },
    };
    expect(recurrenceIsComplete(spec)).toBe(false);
  });

  it('accepts an end date on the anchor day itself', () => {
    const spec: RecurrenceSpec = {
      ...emptyRecurrence('2026-09-10'),
      end: { kind: 'on_date', on_date: '2026-09-10', after_count: null },
    };
    expect(recurrenceIsComplete(spec)).toBe(true);
  });
});
