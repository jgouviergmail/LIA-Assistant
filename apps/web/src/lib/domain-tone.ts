/**
 * The colour code of LIA's domains — agenda violet, mails emerald, weather
 * sky… — decided ONCE for every surface that names a domain.
 *
 * The briefing tiles introduced it on their icons; the notification hub's
 * chips (the sources a proactive notification read) now speak the same code,
 * so a reader who learnt « violet is the agenda » on the dashboard reads it
 * again on the alerts page (owner, 2026-10-03). Before, those chips were grey,
 * the colour the design rules reserve for INACTIVE elements.
 *
 * Classes are written out literally: Tailwind only generates what it can read
 * in the source.
 */

export type DomainTone =
  | 'sky'
  | 'violet'
  | 'amber'
  | 'rose'
  | 'emerald'
  | 'red'
  | 'fuchsia'
  | 'teal'
  | 'indigo'
  | 'orange';

/** An icon in the domain's colour. */
export const DOMAIN_ICON_TONE: Record<DomainTone, string> = {
  sky: 'text-sky-600 dark:text-sky-400',
  violet: 'text-violet-600 dark:text-violet-400',
  amber: 'text-amber-600 dark:text-amber-400',
  rose: 'text-rose-600 dark:text-rose-400',
  emerald: 'text-emerald-600 dark:text-emerald-400',
  red: 'text-red-600 dark:text-red-400',
  fuchsia: 'text-fuchsia-600 dark:text-fuchsia-400',
  teal: 'text-teal-600 dark:text-teal-400',
  indigo: 'text-indigo-600 dark:text-indigo-400',
  orange: 'text-orange-600 dark:text-orange-400',
};

/**
 * A chip in the domain's colour: a faint tint, a border and an ink dark
 * enough for small text on the card in both themes (the 700 / 300 steps).
 */
export const DOMAIN_CHIP_TONE: Record<DomainTone, string> = {
  sky: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  violet: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  amber: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  rose: 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300',
  emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  red: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  fuchsia: 'border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
  teal: 'border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-300',
  indigo: 'border-indigo-500/30 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300',
  orange: 'border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-300',
};

/**
 * A chip with no domain of its own (a trigger, a provider, a source added
 * later): the theme's primary — an ACTIVE fact, so never the inactive grey.
 */
export const THEME_CHIP_TONE = 'border-primary/30 bg-primary/10 text-primary';

/**
 * The domain of each source a proactive notification may have read
 * (`heartbeat` `sources_used`), in the briefing tiles' code. A source absent
 * from this table takes {@link THEME_CHIP_TONE}.
 */
export const HEARTBEAT_SOURCE_TONE: Readonly<Record<string, DomainTone>> = {
  UPCOMING_CALENDAR_EVENTS: 'violet',
  PENDING_TASKS: 'teal',
  UNREAD_EMAILS: 'emerald',
  CURRENT_WEATHER: 'sky',
  WEATHER_CHANGES: 'sky',
  USER_INTERESTS: 'fuchsia',
  USER_MEMORIES: 'indigo',
  JOURNAL_ENTRIES: 'indigo',
  HEALTH_SIGNALS: 'red',
  UPCOMING_BIRTHDAYS: 'rose',
  OPEN_LOOPS: 'amber',
  WORKBOARD: 'orange',
};

/** The chip classes of a heartbeat source, its domain's or the theme's. */
export function heartbeatSourceChipTone(source: string): string {
  const tone = HEARTBEAT_SOURCE_TONE[source];
  return tone ? DOMAIN_CHIP_TONE[tone] : THEME_CHIP_TONE;
}
