/**
 * Naming the SHAPE of a weekly schedule (layout program, 2026-08-05).
 *
 * "Mon, Tue, Wed, Thu, Fri - 08:00" makes the reader parse five tokens to
 * recognise the single most common routine there is. The three shapes people
 * actually schedule get a name — every day, weekdays, the weekend — and only a
 * genuinely irregular pick falls back to the day list.
 *
 * Pure classification only: the wording lives in the locale files
 * (`scheduled_actions.schedule.*`), never here.
 */

/** ISO weekday numbers: 1 = Monday … 7 = Sunday. */
const DAILY = new Set([1, 2, 3, 4, 5, 6, 7]);
const WEEKDAYS = new Set([1, 2, 3, 4, 5]);
const WEEKEND = new Set([6, 7]);

export type ScheduleShape = 'daily' | 'weekdays' | 'weekend' | 'custom';

function sameSet(days: Set<number>, reference: Set<number>): boolean {
  if (days.size !== reference.size) return false;
  for (const day of days) if (!reference.has(day)) return false;
  return true;
}

/**
 * Classify a set of ISO weekdays into a nameable shape.
 *
 * Args:
 *   daysOfWeek: ISO weekday numbers (1-7), any order, duplicates tolerated.
 *
 * Returns:
 *   The shape token the schedule line translates from.
 */
export function scheduleShape(daysOfWeek: readonly number[]): ScheduleShape {
  const days = new Set(daysOfWeek);
  if (sameSet(days, DAILY)) return 'daily';
  if (sameSet(days, WEEKDAYS)) return 'weekdays';
  if (sameSet(days, WEEKEND)) return 'weekend';
  return 'custom';
}
