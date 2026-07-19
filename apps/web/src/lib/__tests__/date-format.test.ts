import { describe, it, expect } from 'vitest';

import { formatLocalDateInput } from '@/lib/date-format';

/**
 * Audit F036: consumption-export dates were computed with
 * `new Date(...).toISOString().split('T')[0]`, which shifts to UTC and rolls
 * civil dates back a day in positive-offset timezones. `formatLocalDateInput`
 * reads local calendar fields, so these assertions hold in EVERY timezone:
 * `new Date(y, m, d, ...)` and `getFullYear/getMonth/getDate` are inverse
 * operations on the local calendar, independent of the runtime TZ.
 */
describe('formatLocalDateInput', () => {
  it('formats a plain local date as YYYY-MM-DD', () => {
    expect(formatLocalDateInput(new Date(2026, 5, 15))).toBe('2026-06-15');
  });

  it('zero-pads single-digit months and days', () => {
    expect(formatLocalDateInput(new Date(2026, 0, 3))).toBe('2026-01-03');
    expect(formatLocalDateInput(new Date(2026, 8, 9))).toBe('2026-09-09');
  });

  it('returns the 1st for local midnight on the 1st (the F036 failure case)', () => {
    // In Europe/Paris this instant is 2025-12-31T23:00Z, so the old UTC path
    // yielded "2025-12-31". The local calendar day is the 1st, in every TZ.
    expect(formatLocalDateInput(new Date(2026, 0, 1, 0, 0))).toBe('2026-01-01');
  });

  it('keeps the correct year on a late-night year boundary', () => {
    expect(formatLocalDateInput(new Date(2025, 11, 31, 23, 30))).toBe('2025-12-31');
  });

  it('handles the last day of a month (month index is +1)', () => {
    expect(formatLocalDateInput(new Date(2026, 11, 31))).toBe('2026-12-31');
  });

  it('handles a leap day', () => {
    expect(formatLocalDateInput(new Date(2024, 1, 29))).toBe('2024-02-29');
  });

  it('agrees with the local calendar fields for an arbitrary UTC instant', () => {
    const d = new Date('2026-03-10T22:45:00Z');
    const expected = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
      d.getDate()
    ).padStart(2, '0')}`;
    expect(formatLocalDateInput(d)).toBe(expected);
  });
});
