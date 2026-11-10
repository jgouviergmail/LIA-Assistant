/**
 * Labels the habits surfaces share: a weekday by its index, in the reader's
 * language. Hours use `clockLabel` (`@/lib/recurrence`): digits are the same
 * in every language.
 */

/**
 * The full name of a weekday.
 *
 * @param locale - BCP-47 locale of the reader.
 * @param dow - 0 = Monday … 6 = Sunday (the backend's `date.weekday()`).
 */
export function weekdayName(locale: string, dow: number): string {
  // 2026-08-03 is a Monday; offsetting from it yields any weekday safely.
  const reference = new Date(Date.UTC(2026, 7, 3 + dow));
  return new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(reference);
}
