/**
 * « Remind me » (ADR-372, lot 1): the moments the page offers, on the account's wall.
 *
 * The reminders' route reads a wall clock in the account's zone, so the page writes one and never
 * an offset. A moment is `YYYY-MM-DDTHH:MM`, as a native `datetime-local` field writes it.
 */
import { addDays, instantToWall, wallTimeToInstant } from './calendar/zoned';

/** Where an evening starts and a morning is offered, on the wall. */
const EVENING = '18:00';
const MORNING = '09:00';
const MONDAY = 1;
const MOMENT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

/** One moment offered in a press. */
export interface RemindChoice {
  /** Its word: `workbench.assist.remind.choices.<key>`. */
  key: 'evening' | 'tomorrow' | 'next_week';
  at: string;
}

function weekday(date: string): number {
  return new Date(`${date}T00:00:00Z`).getUTCDay();
}

/** The first Monday past tomorrow: from a Sunday, tomorrow says the one that follows. */
function nextMonday(today: string): string {
  const ahead = (MONDAY - weekday(today) + 7) % 7 || 7;
  return addDays(today, ahead === 1 ? 8 : ahead);
}

/**
 * @param now - The present instant.
 * @param zone - The account's zone.
 * @returns What can be offered now: this evening only while it has not started.
 */
export function remindChoices(now: Date, zone: string): readonly RemindChoice[] {
  const { date, time } = instantToWall(now, zone);
  const evening: readonly RemindChoice[] =
    time < EVENING ? [{ key: 'evening', at: `${date}T${EVENING}` }] : [];
  return [
    ...evening,
    { key: 'tomorrow', at: `${addDays(date, 1)}T${MORNING}` },
    { key: 'next_week', at: `${nextMonday(date)}T${MORNING}` },
  ];
}

/**
 * @param moment - What the field holds.
 * @param now - The present instant.
 * @param zone - The account's zone.
 * @returns Whether it can be read and is still to come.
 */
export function isStillAhead(moment: string, now: Date, zone: string): boolean {
  if (!MOMENT.test(moment)) return false;
  const [date, time] = moment.split('T');
  return wallTimeToInstant(date, time, zone).getTime() > now.getTime();
}

/** @returns The moment as the route reads it: a wall clock, seconds written. */
export function reminderInstant(moment: string): string {
  return `${moment}:00`;
}
