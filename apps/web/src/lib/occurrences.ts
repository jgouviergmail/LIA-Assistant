/**
 * Rendering a routine's upcoming runs, in the routine's own timezone.
 *
 * The instants come from the backend scheduler — the same APScheduler cron the
 * executor fires from. Nothing here re-derives a schedule: a second
 * interpretation of the cron would be a second authority, and the two would
 * disagree exactly where it matters (the daylight-saving edges).
 *
 * Two rules the display must respect:
 *
 * - **The routine's timezone, not the reader's.** A routine evaluated in
 *   `Europe/Paris` fires at 08:00 Paris whether the reader is in Paris or in
 *   Tokyo. Rendering in the browser's zone would announce hours the routine
 *   will not run at.
 * - **The clocks may change between two runs.** When they do, the wall-clock
 *   time is unchanged but the instant shifts by an hour — worth saying, since
 *   a reader comparing two lines would otherwise see no difference at all.
 */

/** One upcoming run, ready to render. */
export interface RenderedOccurrence {
  /** The instant, ISO-8601 UTC — a stable key and a `dateTime` attribute. */
  iso: string;
  /** Date + time in the routine's zone, localized. */
  label: string;
  /** Short zone name at that instant (e.g. `CET`, `CEST`). */
  zone: string;
  /**
   * True when this run's zone differs from the previous one's — i.e. the
   * clocks change between them.
   */
  clockChange: boolean;
}

/**
 * Formatter cache, keyed by (locale, zone, kind).
 *
 * `Intl.DateTimeFormat` is expensive to construct and these are identical from
 * one render to the next. Measured before caching: 18.9 ms to render twenty
 * routines × five occurrences — and the routines list re-renders on every
 * keystroke in its create/edit form, which on a mid-range phone puts a single
 * keypress past the 30 ms the repo treats as a component defect.
 *
 * Bounded by construction: the key space is (the app's six locales) × (the
 * zones the user's own routines use) × 2, so it cannot grow with time or data.
 */
const formatterCache = new Map<string, Intl.DateTimeFormat>();

function cachedFormatter(
  locale: string,
  options: Intl.DateTimeFormatOptions,
  kind: string
): Intl.DateTimeFormat | null {
  const key = `${kind}|${locale}|${options.timeZone ?? ''}`;
  const hit = formatterCache.get(key);
  if (hit) return hit;
  try {
    const formatter = new Intl.DateTimeFormat(locale, options);
    formatterCache.set(key, formatter);
    return formatter;
  } catch {
    // An unknown zone or locale: the caller falls back rather than throwing.
    return null;
  }
}

/**
 * Read the short timezone name for an instant, in a given zone.
 *
 * `Intl` is the only source that knows whether an instant is in summer time:
 * comparing UTC offsets by hand would mean re-implementing the tz database.
 */
function zoneNameAt(date: Date, timeZone: string, locale: string): string {
  const formatter = cachedFormatter(locale, { timeZone, timeZoneName: 'short' }, 'zone');
  if (!formatter) return '';
  const parts = formatter.formatToParts(date);
  return parts.find(part => part.type === 'timeZoneName')?.value ?? '';
}

/**
 * Format the upcoming runs for display.
 *
 * @param isoInstants - UTC instants from the API, in order.
 * @param timeZone - The routine's IANA timezone.
 * @param locale - BCP-47 locale for wording and ordering.
 * @returns One entry per instant; an unparseable one is dropped rather than
 *   rendered as `Invalid Date`.
 */
export function renderOccurrences(
  isoInstants: string[],
  timeZone: string,
  locale: string
): RenderedOccurrence[] {
  const rendered: RenderedOccurrence[] = [];
  let previousZone: string | null = null;

  for (const iso of isoInstants) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) continue;

    const shape: Intl.DateTimeFormatOptions = {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    };
    // An unknown zone must not blank the whole list: fall back to the reader's
    // own, which is wrong but readable, rather than throwing.
    const formatter =
      cachedFormatter(locale, { ...shape, timeZone }, 'label') ??
      cachedFormatter(locale, shape, 'label-fallback');
    const label = formatter ? formatter.format(date) : date.toISOString();

    const zone = zoneNameAt(date, timeZone, locale);
    rendered.push({
      iso,
      label,
      zone,
      // Only a CHANGE is flagged, never the first entry: there is nothing to
      // compare it against, and marking it would suggest a transition that is
      // not happening.
      clockChange: previousZone !== null && zone !== '' && zone !== previousZone,
    });
    if (zone !== '') previousZone = zone;
  }

  return rendered;
}
