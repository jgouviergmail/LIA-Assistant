/**
 * Suffix per unit the diagnostics API publishes (`KNOWN_UNITS` on the backend,
 * plus the catalogue's `percent`/`seconds`/`count`). ONE table for the check
 * rows and the evidence pack: a value shown twice with two suffixes is a value
 * an administrator cannot trust. An unlisted unit renders bare, never guessed.
 * `ms` keeps a NO-BREAK space so the unit cannot wrap away from its number in a
 * narrow column.
 */
export const UNIT_SUFFIX: Record<string, string> = {
  percent: '%',
  seconds: 's',
  milliseconds: ' ms',
  count: '',
};

/** The suffix for a unit, or nothing for an unknown or absent one. */
export function unitSuffix(unit: string | undefined): string {
  return unit ? (UNIT_SUFFIX[unit] ?? '') : '';
}
