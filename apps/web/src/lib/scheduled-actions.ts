/**
 * Pure helpers for the recurring-routines studio.
 *
 * Lives in `lib/` rather than beside the section component: a settings section
 * file must export exactly ONE component (asserted by
 * `settings-sections.test.ts`, which parses those files to check the
 * deep-link table), so a helper worth testing on its own belongs here.
 */

import type {
  ScheduledAction,
  ScheduledActionWeekCell,
  ScheduledActionWeekResponse,
} from '@/hooks/useScheduledActions';
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

// =============================================================================
// Chronological order and numbering (ADR-265)
// =============================================================================

/** A routine with its rank in trigger-time order, 1-based. */
export interface NumberedAction {
  action: ScheduledAction;
  number: number;
}

/**
 * Order two routines by the time of day they fire at.
 *
 * Hour, then minute, then the title in the reader's language (numeric, so
 * "Routine 2" precedes "Routine 10"; accent-insensitive), then the id — so the
 * order is total and the numbers it produces are deterministic whatever order
 * the API returned the rows in.
 *
 * The API's own order (`next_trigger_at`) is deliberately NOT used: it moves
 * every day as runs happen, and three other readers depend on it (the hub,
 * the briefing, the automation tool), so the sort lives here, at the display.
 */
export function compareByTriggerTime(
  a: ScheduledAction,
  b: ScheduledAction,
  collator: Intl.Collator
): number {
  return (
    a.trigger_hour - b.trigger_hour ||
    a.trigger_minute - b.trigger_minute ||
    collator.compare(a.title, b.title) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

/**
 * Number the routines in trigger-time order.
 *
 * A paused routine keeps its rank: toggling never renumbers, so the number a
 * reader memorised on the timeline still names the same card. Creating or
 * rescheduling a routine does renumber — a rank is an order, not an identity.
 *
 * @param actions - The routines, in any order.
 * @param locale - BCP-47 locale for the title tie-break.
 */
export function numberByTriggerTime(
  actions: readonly ScheduledAction[],
  locale: string
): NumberedAction[] {
  const collator = new Intl.Collator(locale, { sensitivity: 'base', numeric: true });
  return [...actions]
    .sort((a, b) => compareByTriggerTime(a, b, collator))
    .map((action, index) => ({ action, number: index + 1 }));
}

/** `HH:MM` of a routine's trigger, as configured (wall clock in its zone). */
export function triggerTimeLabel(action: Pick<ScheduledAction, 'trigger_hour' | 'trigger_minute'>) {
  return `${String(action.trigger_hour).padStart(2, '0')}:${String(action.trigger_minute).padStart(2, '0')}`;
}

// =============================================================================
// The grid: hours × days
// =============================================================================

/** ISO weekdays, Monday first — the form and the grid agree on this. */
export const ISO_WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

/** The 24 hour rows of the grid. */
export const GRID_HOURS = Array.from({ length: 24 }, (_, hour) => hour);

/** One chip in one cell of the grid. */
export interface TimelineEntry {
  number: number;
  action: ScheduledAction;
  /** The week's facts for that routine on that day; null when unknown. */
  cell: ScheduledActionWeekCell | null;
}

/** Key of a grid cell. */
export function timelineKey(day: number, hour: number): string {
  return `${day}:${hour}`;
}

/**
 * Place every routine on its days, at its hour.
 *
 * The grid speaks in the WALL CLOCK of each routine's own schedule: a routine
 * at 08:00 sits on row 8 whatever the zone, and the zone is named beside the
 * grid. Minutes do not move a chip (the row is the hour); they order the
 * chips inside a cell and appear in the chip's name. Out-of-range days or
 * hours are skipped rather than crashing the grid, and a day listed twice is
 * placed once.
 *
 * @param numbered - Routines in chronological order (`numberByTriggerTime`).
 * @param week - The current week's states, or null when unavailable.
 */
export function buildTimelineGrid(
  numbered: readonly NumberedAction[],
  week: ScheduledActionWeekResponse | null
): Map<string, TimelineEntry[]> {
  const weekByAction = new Map(week?.actions.map(w => [w.id, w]) ?? []);
  const grid = new Map<string, TimelineEntry[]>();
  for (const entry of numbered) {
    const { action } = entry;
    if (action.trigger_hour < 0 || action.trigger_hour > 23) continue;
    const cells = weekByAction.get(action.id)?.cells ?? [];
    for (const day of new Set(action.days_of_week)) {
      if (day < 1 || day > 7) continue;
      const key = timelineKey(day, action.trigger_hour);
      const bucket = grid.get(key) ?? [];
      bucket.push({
        number: entry.number,
        action,
        cell: cells.find(c => c.day === day) ?? null,
      });
      grid.set(key, bucket);
    }
  }
  return grid;
}

// =============================================================================
// What a chip says
// =============================================================================

/** The colour of a chip — one tone per fact the reader asked for. */
export type ChipTone = 'idle' | 'success' | 'failure' | 'proposed' | 'paused';

/** Why an idle chip is idle, when there is a reason worth stating. */
export type ChipReason = 'skipped_condition' | 'skipped_hitl';

export interface ChipState {
  tone: ChipTone;
  reason: ChipReason | null;
  /** The routine is running right now. */
  executing: boolean;
}

/**
 * Decide a chip's state from the routine and the week's facts for its day.
 *
 * Paused outranks everything: a routine that is switched off is inert, and
 * greying it says so before any history does. Then the last run of the slot:
 * success, failure, or a proposal waiting for the reader's click. A skip keeps
 * the idle colour — nothing ran — but carries its reason, because "not run"
 * and "the condition was not met" are different answers to "why is it white?".
 */
export function chipState(
  action: ScheduledAction,
  cell: ScheduledActionWeekCell | null
): ChipState {
  const executing = action.status === 'executing';
  if (!action.is_enabled) return { tone: 'paused', reason: null, executing };
  switch (cell?.outcome) {
    case 'success':
      return { tone: 'success', reason: null, executing };
    case 'failure':
      return { tone: 'failure', reason: null, executing };
    case 'proposed':
      return { tone: 'proposed', reason: null, executing };
    case 'skipped_condition':
    case 'skipped_hitl':
      return { tone: 'idle', reason: cell.outcome, executing };
    default:
      return { tone: 'idle', reason: null, executing };
  }
}

// =============================================================================
// Zones and dates
// =============================================================================

/** The distinct zones the routines are scheduled in, first seen first. */
export function routineZones(actions: readonly Pick<ScheduledAction, 'user_timezone'>[]): string[] {
  return [...new Set(actions.map(a => a.user_timezone))];
}

/** en-US short weekday names, in ISO order (index 0 = Monday). */
const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/**
 * The ISO weekday of an instant in a zone, or null when the zone is unknown.
 *
 * `Intl` is the only thing here that reads a zone, and it reads a NAME, never
 * a schedule: this is the fallback for the column to highlight when the
 * server's week is unavailable, not a second reading of the cron.
 */
export function isoWeekdayInZone(instant: Date, timeZone: string): number | null {
  try {
    const name = new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'short' }).format(instant);
    const index = WEEKDAY_NAMES.indexOf(name);
    return index === -1 ? null : index + 1;
  } catch {
    return null;
  }
}

/**
 * The seven calendar dates of a week, Monday first, from its `YYYY-MM-DD` start.
 *
 * Pure calendar arithmetic in UTC: the week start is a local DATE, not an
 * instant, so no zone must ever touch it.
 */
export function weekDates(weekStart: string): string[] {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(weekStart);
  if (!match) return [];
  const [, y, m, d] = match;
  return ISO_WEEKDAYS.map(offset => {
    const date = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d) + offset - 1));
    return date.toISOString().slice(0, 10);
  });
}

/** DOM id of a routine's card — the target a grid chip scrolls and focuses. */
export function routineCardId(actionId: string): string {
  return `routine-card-${actionId}`;
}

// =============================================================================
// Keyboard: the grid is ONE tab stop
// =============================================================================

/** Identity of a chip on the grid: a routine on a day. */
export function chipKey(actionId: string, day: number): string {
  return `${actionId}:${day}`;
}

/** Keys that move the roving focus; anything else is left to the browser. */
export type RovingKey = 'ArrowRight' | 'ArrowDown' | 'ArrowLeft' | 'ArrowUp' | 'Home' | 'End';

/**
 * The chip to focus after a key press, or null when the key does not move.
 *
 * Fifty routines draw up to 350 chips; as individual tab stops they would
 * stand between the reader and the cards. The grid is therefore ONE stop and
 * the arrows walk it in reading order (rows, then days), wrapping at the
 * ends, with Home/End for the extremes. A current key that is no longer on
 * the grid (a routine deleted under the reader's finger) restarts from the
 * first chip.
 */
export function rovingTarget(keys: readonly string[], current: string | null, key: string) {
  if (keys.length === 0) return null;
  const index = current === null ? -1 : keys.indexOf(current);
  switch (key) {
    case 'ArrowRight':
    case 'ArrowDown':
      return keys[index === -1 ? 0 : (index + 1) % keys.length] ?? null;
    case 'ArrowLeft':
    case 'ArrowUp':
      return keys[index === -1 ? 0 : (index - 1 + keys.length) % keys.length] ?? null;
    case 'Home':
      return keys[0] ?? null;
    case 'End':
      return keys[keys.length - 1] ?? null;
    default:
      return null;
  }
}
