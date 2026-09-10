/**
 * A due DATE, between the field a person types in and the instant we store.
 *
 * `<input type="date">` speaks days (`YYYY-MM-DD`); the API stores an instant.
 * Converting between the two is where a deadline quietly moves, so it is done
 * once, here, rather than at each control.
 *
 * Two decisions, both measured:
 *
 * - **the instant is the END of the chosen day, in the reader's own zone.**
 *   `new Date('2026-09-15').toISOString()` is midnight UTC, which made a
 *   ticket overdue at midday on its own due date — a full day of the breathing
 *   red frame lot 21 built for real lateness. A day-granular deadline means
 *   « by the end of that day », and that is what is stored.
 * - **the field is derived from the instant in local time, never sliced off
 *   the ISO string.** `iso.slice(0, 10)` is the UTC day: west of Greenwich it
 *   showed the day after the one the person picked, and east of it the day
 *   before whenever the instant sat near a boundary.
 *
 * Both functions answer « nothing » for nothing: a blank field is a deadline
 * being REMOVED, and the caller sends `clear_due_at` rather than an instant.
 */

/**
 * The day a stored instant falls on, in the reader's own timezone.
 *
 * @param iso - The stored `due_at`, or null.
 * @returns `YYYY-MM-DD` for the `<input type="date">`, or `''` when there is
 *   no date to show — an unparsable value included, which is a field that
 *   must stay empty rather than show `NaN-NaN-NaN`.
 */
export function dueDateInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return '';
  // Local getters, never `toISOString()`: the day is the reader's, not UTC's.
  const year = instant.getFullYear();
  const month = String(instant.getMonth() + 1).padStart(2, '0');
  const day = String(instant.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * The instant a chosen day means: its last second, locally.
 *
 * @param value - What the date field holds (`YYYY-MM-DD`), possibly blank.
 * @returns The ISO instant to store, or null when the field says nothing —
 *   the caller then clears the deadline instead of setting one.
 */
export function dueAtFromInput(value: string): string | null {
  const day = value.trim();
  if (!day) return null;
  // No `Z` and no offset: ECMAScript parses a date-TIME form as LOCAL time,
  // which is exactly the reading a person means by « the 15th ».
  const instant = new Date(`${day}T23:59:59`);
  if (Number.isNaN(instant.getTime())) return null;
  return instant.toISOString();
}
