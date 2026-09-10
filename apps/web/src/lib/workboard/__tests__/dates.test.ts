/**
 * A due DATE is a day, and it is the reader's day (ADR-276).
 *
 * The board's two date controls sent `new Date('2026-09-15').toISOString()`,
 * which is MIDNIGHT UTC of that day. Measured, in two timezones:
 *
 * - `America/New_York`: picking « 15 September » drew **14/09** on the card —
 *   the date read back was not the date typed;
 * - `Europe/Paris` and `America/New_York` alike: the ticket was **overdue at
 *   midday on its own due date**, so the breathing red frame lot 21 built for
 *   lateness fired a full day early.
 *
 * The properties below hold in EVERY timezone, which is why they are written
 * as properties rather than as expected strings: the suite must not depend on
 * the machine that runs it.
 */
import { describe, expect, it } from 'vitest';

import { dueAtFromInput, dueDateInput } from '@/lib/workboard/dates';
import { isOverdue } from '@/lib/workboard/display';

const DAYS = ['2026-01-01', '2026-03-29', '2026-06-15', '2026-09-15', '2026-12-31'];

/** The instant a real day maps to — never null, and the type says so. */
function instantFor(day: string): string {
  const stored = dueAtFromInput(day);
  if (stored === null) throw new Error(`no instant for ${day}`);
  return stored;
}

describe('a due date survives the round trip', () => {
  it.each(DAYS)('reads back exactly the day that was picked (%s)', day => {
    expect(dueDateInput(instantFor(day))).toBe(day);
  });

  it('shows the picked day on the card, whatever the offset', () => {
    for (const day of DAYS) {
      const shown = new Intl.DateTimeFormat('en-CA', { dateStyle: 'short' }).format(
        new Date(instantFor(day))
      );
      // `en-CA` short is ISO-shaped, so the comparison is the day itself.
      expect(shown).toBe(day);
    }
  });
});

describe('lateness starts at the END of the due day', () => {
  const ticket = (due: string) => ({ due_at: due, status: 'todo' });

  it.each(DAYS)('is not overdue at midday of its own due date (%s)', day => {
    const midday = new Date(`${day}T12:00:00`);
    expect(isOverdue(ticket(instantFor(day)), midday)).toBe(false);
  });

  it.each(DAYS)('is not overdue one second before the day ends (%s)', day => {
    const almost = new Date(`${day}T23:59:00`);
    expect(isOverdue(ticket(instantFor(day)), almost)).toBe(false);
  });

  it.each(DAYS)('IS overdue once the next day has started (%s)', day => {
    const nextDay = new Date(`${day}T23:59:59`);
    nextDay.setSeconds(nextDay.getSeconds() + 2);
    expect(isOverdue(ticket(instantFor(day)), nextDay)).toBe(true);
  });
});

describe('an absent date is absent', () => {
  it('reads nothing from nothing', () => {
    expect(dueDateInput(null)).toBe('');
    expect(dueDateInput('')).toBe('');
  });

  it('never invents an instant from a blank field', () => {
    expect(dueAtFromInput('')).toBeNull();
    expect(dueAtFromInput('   ')).toBeNull();
  });

  it('refuses a value that is not a day rather than storing an Invalid Date', () => {
    // `<input type="date">` cannot produce this; a URL or an old draft can.
    expect(dueAtFromInput('not-a-date')).toBeNull();
    expect(dueDateInput('not-an-instant')).toBe('');
  });
});
