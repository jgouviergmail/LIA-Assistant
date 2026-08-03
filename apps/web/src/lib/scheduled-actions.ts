/**
 * Pure helpers for the recurring-routines studio.
 *
 * Lives in `lib/` rather than beside the section component: a settings section
 * file must export exactly ONE component (asserted by
 * `settings-sections.test.ts`, which parses those files to check the
 * deep-link table), so a helper worth testing on its own belongs here.
 */

import { SCHEDULED_ACTION_TITLE_MAX_LENGTH } from '@/lib/constants';

/**
 * Title of a duplicated routine: the source, marked as a copy, within bounds.
 *
 * When the pair does not fit `title`'s column bound, the TITLE is trimmed
 * rather than the mark — losing the mark would leave two identically-named
 * routines, which is exactly what the reader is duplicating to avoid. An
 * absurdly long mark degrades to the mark alone rather than overflowing,
 * because the API would refuse the create outright.
 *
 * @param title - Title of the routine being duplicated.
 * @param suffix - Localized copy marker.
 * @returns A title at most `SCHEDULED_ACTION_TITLE_MAX_LENGTH` long.
 */
export function duplicateTitle(title: string, suffix: string): string {
  const combined = `${title} ${suffix}`;
  if (combined.length <= SCHEDULED_ACTION_TITLE_MAX_LENGTH) return combined;
  const room = SCHEDULED_ACTION_TITLE_MAX_LENGTH - suffix.length - 1;
  return room > 0
    ? `${trimToUnits(title, room)} ${suffix}`
    : trimToUnits(suffix, SCHEDULED_ACTION_TITLE_MAX_LENGTH);
}

/**
 * Cut a string to at most `units` UTF-16 code units, never mid-character.
 *
 * `slice` counts code units, and an emoji is two of them: a cut landing
 * between the pair leaves a lone surrogate, which renders as the replacement
 * glyph and is not well-formed text to send to an API. "🏃 Course du matin"
 * is an ordinary routine title, so this is reachable, not theoretical.
 *
 * @param value - Text to shorten.
 * @param units - Hard upper bound, in the units the column counts.
 * @returns `value` cut to at most `units`, one code unit shorter when the
 *   boundary would have split a pair.
 */
function trimToUnits(value: string, units: number): string {
  if (value.length <= units) return value;
  const cut = value.slice(0, units);
  // A trailing HIGH surrogate means its partner was left behind.
  return /[\uD800-\uDBFF]$/.test(cut) ? cut.slice(0, -1) : cut;
}
