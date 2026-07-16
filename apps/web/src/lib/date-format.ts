/**
 * Civil-date formatting helpers for `<input type="date">` values and export
 * ranges — always in the viewer's LOCAL calendar, never UTC.
 */

/**
 * Format a {@link Date} as a civil calendar date `"YYYY-MM-DD"` using the
 * runtime's LOCAL timezone fields.
 *
 * Prefer this over `date.toISOString().split('T')[0]`, which converts to UTC
 * first: in any positive-offset timezone (e.g. Europe/Paris) a date near
 * midnight then rolls back to the previous day, producing the wrong civil date
 * for a date input or an export range (audit F036). Reading
 * `getFullYear`/`getMonth`/`getDate` yields the user's actual local calendar
 * day in every timezone.
 *
 * @param date - The instant to format.
 * @returns The local civil date as `YYYY-MM-DD` (zero-padded).
 */
export function formatLocalDateInput(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
