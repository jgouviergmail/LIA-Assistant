/**
 * « Remind me » (lot 1): the moments offered are read on the account's wall, whatever the clock of
 * the device says, and a moment already gone is never sent.
 */
import { describe, expect, it } from 'vitest';

import { isStillAhead, remindChoices, reminderInstant } from '../reminding';

const PARIS = 'Europe/Paris';
/** A Wednesday, 10:00 in Paris. */
const MORNING = new Date('2026-11-04T09:00:00Z');
/** The same Wednesday, 20:00 in Paris. */
const NIGHT = new Date('2026-11-04T19:00:00Z');
/** A Sunday, 10:00 in Paris. */
const SUNDAY = new Date('2026-11-08T09:00:00Z');

function byKey(now: Date, zone = PARIS) {
  return Object.fromEntries(remindChoices(now, zone).map(choice => [choice.key, choice.at]));
}

describe('remindChoices', () => {
  it('offers this evening, tomorrow morning and next week', () => {
    expect(byKey(MORNING)).toEqual({
      evening: '2026-11-04T18:00',
      tomorrow: '2026-11-05T09:00',
      next_week: '2026-11-09T09:00',
    });
  });

  it('leaves this evening out once it has started', () => {
    expect(byKey(NIGHT)).toEqual({
      tomorrow: '2026-11-05T09:00',
      next_week: '2026-11-09T09:00',
    });
  });

  it('never offers the same morning twice: from a Sunday, next week is the week after tomorrow', () => {
    expect(byKey(SUNDAY).tomorrow).toBe('2026-11-09T09:00');
    expect(byKey(SUNDAY).next_week).toBe('2026-11-16T09:00');
  });

  it('reads the day on the account’s wall, never on the device’s', () => {
    // 23:30 UTC is already tomorrow in Tokyo.
    const late = new Date('2026-11-04T23:30:00Z');

    expect(byKey(late, 'Asia/Tokyo').tomorrow).toBe('2026-11-06T09:00');
    expect(byKey(late, 'America/New_York').tomorrow).toBe('2026-11-05T09:00');
  });
});

describe('isStillAhead', () => {
  it('takes a moment on the account’s wall that is still to come', () => {
    expect(isStillAhead('2026-11-04T10:01', MORNING, PARIS)).toBe(true);
  });

  it('refuses the minute that just went', () => {
    expect(isStillAhead('2026-11-04T10:00', MORNING, PARIS)).toBe(false);
  });

  it('refuses a moment nobody can read', () => {
    expect(isStillAhead('', MORNING, PARIS)).toBe(false);
    expect(isStillAhead('tomorrow', MORNING, PARIS)).toBe(false);
  });
});

describe('reminderInstant', () => {
  it('sends the wall clock as the route reads it: no zone, no offset', () => {
    expect(reminderInstant('2026-11-05T09:00')).toBe('2026-11-05T09:00:00');
  });
});
