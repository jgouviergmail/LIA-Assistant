/**
 * Pure helpers for the generic recurrence editor.
 *
 * Domain-free: nothing here knows about routines or reminders, so a second
 * consumer mounts the editor without touching this file.
 *
 * **These helpers are never the authority on a schedule.** The server computes
 * the instants and publishes them (`times_of_day`, `next_occurrences`,
 * `schedule_display`); a rendered card always reads those. `materialisedTimes`
 * exists for ONE reason: the editor must show what a step produces while the
 * reader is still choosing it, and no round trip can answer that between two
 * keystrokes. It is a preview, and the moment a routine is saved the server's
 * answer replaces it.
 */

import type {
  DailyTimes,
  RecurrenceFreq,
  RecurrenceSpec,
  TimeOfDay,
} from '@/types/recurrence';

/** ISO weekdays, Monday first — the picker and the grid agree on this. */
export const ISO_WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

/** The last working day: where the weekday picker breaks so the weekend groups. */
export const FRIDAY = 5;

/** The three day sets that deserve a name instead of a list. */
export const WEEKDAY_SETS = {
  all: [1, 2, 3, 4, 5, 6, 7],
  workdays: [1, 2, 3, 4, 5],
  weekend: [6, 7],
} as const;

/** Most moments a preview will expand, whatever the caller's own cap. */
const PREVIEW_TIMES_CEILING = 48;

/** Smallest step a preview will expand — below it, a day is unbounded. */
const MIN_PREVIEW_STEP_MINUTES = 5;

export type NamedDaySet = keyof typeof WEEKDAY_SETS;

/**
 * The named shape of a weekday selection, or null when it is irregular.
 *
 * @param days - ISO weekdays, any order, duplicates tolerated.
 */
export function namedDaySet(days: readonly number[]): NamedDaySet | null {
  const chosen = [...new Set(days)].sort((a, b) => a - b).join(',');
  for (const [name, set] of Object.entries(WEEKDAY_SETS)) {
    if (set.join(',') === chosen) return name as NamedDaySet;
  }
  return null;
}

/** `HH:MM` — digits, identical in every language. */
export function clockLabel(moment: TimeOfDay): string {
  return `${String(moment.hour).padStart(2, '0')}:${String(moment.minute).padStart(2, '0')}`;
}

const minutesOf = (moment: TimeOfDay) => moment.hour * 60 + moment.minute;

/**
 * The moments of one served day — **a preview**, not an authority.
 *
 * Bounded twice: a step below `MIN_PREVIEW_STEP_MINUTES` would make a day
 * unbounded, and the ceiling stops a long window from building a list no
 * screen can show. The server refuses both anyway; refusing them here is what
 * keeps the editor responsive while the reader is still choosing.
 *
 * @param times - The moments, explicit or as a step.
 * @returns The moments, ascending and de-duplicated.
 */
export function materialisedTimes(times: DailyTimes): TimeOfDay[] {
  let moments: TimeOfDay[] = [];
  if (times.mode === 'at') {
    moments = times.at ?? [];
  } else {
    const step = times.step_minutes ?? 0;
    const start = times.start;
    const end = times.end;
    if (step >= MIN_PREVIEW_STEP_MINUTES && start && end) {
      for (
        let cursor = minutesOf(start);
        cursor <= minutesOf(end) && moments.length < PREVIEW_TIMES_CEILING;
        cursor += step
      ) {
        moments.push({ hour: Math.floor(cursor / 60), minute: cursor % 60 });
      }
    }
  }
  const unique = [...new Set(moments.map(minutesOf))].sort((a, b) => a - b);
  return unique.map(total => ({ hour: Math.floor(total / 60), minute: total % 60 }));
}

/** How many times a served day fires — an upper bound (a clock change moves it). */
export function runsPerDay(times: DailyTimes): number {
  return materialisedTimes(times).length;
}

/**
 * The recurrence a reader starts from: every day, once, at 08:00.
 *
 * @param anchor - `YYYY-MM-DD`, the day the series starts.
 */
export function emptyRecurrence(anchor: string): RecurrenceSpec {
  return {
    freq: 'daily',
    interval: 1,
    anchor_date: anchor,
    byweekday: [],
    bymonthday: [],
    bymonth: [],
    nth_weekday: null,
    times: { mode: 'at', at: [{ hour: 8, minute: 0 }] },
    end: { kind: 'never', on_date: null, after_count: null },
  };
}

/**
 * The day selectors each frequency actually reads.
 *
 * The mirror of `SELECTORS_READ_BY` in `core/recurrence/spec.py`, and the
 * reason it has to exist here too: the API refuses a stored selector its
 * engine would ignore, so a residue this editor leaves behind becomes a
 * validation error the reader never caused.
 */
const SELECTORS_READ_BY: Record<RecurrenceFreq, readonly RecurrenceSelector[]> = {
  once: [],
  daily: [],
  weekly: ['byweekday'],
  monthly: ['bymonthday', 'nth_weekday'],
  yearly: ['bymonth', 'bymonthday'],
};

/** The four fields that name WHICH days a recurrence serves. */
type RecurrenceSelector = 'byweekday' | 'bymonthday' | 'bymonth' | 'nth_weekday';

/**
 * Move a recurrence to another frequency, keeping only what it can read.
 *
 * Two failures to avoid, and they pull in opposite directions:
 *
 * - a selector the new frequency NEEDS must be filled — from what is already
 *   there, or from the anchor — or the reader meets "a weekly rule needs a
 *   weekday" for a choice they made in one click;
 * - a selector it never reads must be CLEARED, because the API refuses a
 *   value its engine would ignore. Ticking Monday and Tuesday in weekly and
 *   then switching to daily used to send both, and before 2026-09-06 the API
 *   stored them and fired all seven days.
 *
 * @param spec - The current recurrence.
 * @param freq - The frequency to move to.
 * @returns A complete recurrence at the new frequency, and nothing more.
 */
export function withFreq(spec: RecurrenceSpec, freq: RecurrenceFreq): RecurrenceSpec {
  const anchorDay = Number(spec.anchor_date.slice(8, 10)) || 1;
  const anchorMonth = Number(spec.anchor_date.slice(5, 7)) || 1;
  const anchorWeekday = isoWeekdayOf(spec.anchor_date);
  const reads = SELECTORS_READ_BY[freq];
  const kept = (name: RecurrenceSelector) => reads.includes(name);

  const byweekday = kept('byweekday')
    ? spec.byweekday.length > 0
      ? spec.byweekday
      : [anchorWeekday]
    : [];
  // A monthly rule reads EITHER a day of month or an nth weekday: keeping the
  // nth means leaving the day empty, and the spec refuses carrying both.
  const nth_weekday = kept('nth_weekday') ? spec.nth_weekday : null;
  const needsMonthDay = kept('bymonthday') && nth_weekday === null;
  const bymonthday = needsMonthDay
    ? spec.bymonthday.length > 0
      ? spec.bymonthday
      : [anchorDay]
    : [];
  const bymonth = kept('bymonth')
    ? spec.bymonth.length > 0
      ? spec.bymonth
      : [anchorMonth]
    : [];

  const base: RecurrenceSpec = { ...spec, freq, byweekday, bymonthday, bymonth, nth_weekday };
  if (freq === 'once') {
    return { ...base, interval: 1, end: { kind: 'never', on_date: null, after_count: null } };
  }
  return base;
}

/**
 * The ISO weekday of a `YYYY-MM-DD` date, 1 = Monday.
 *
 * Pure calendar arithmetic in UTC: an anchor is a local DATE, so no timezone
 * must ever touch it.
 */
export function isoWeekdayOf(isoDate: string): number {
  const parsed = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!parsed) return 1;
  const [, y, m, d] = parsed;
  const day = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d))).getUTCDay();
  return day === 0 ? 7 : day;
}

/**
 * Whether a recurrence is complete enough for the API to accept it.
 *
 * Mirrors the server's structural rules so the Save button states what will
 * happen instead of letting a request fail. It does NOT mirror the caps —
 * those are injected per consumer and checked by the editor itself.
 */
export function recurrenceIsComplete(spec: RecurrenceSpec): boolean {
  if (runsPerDay(spec.times) === 0) return false;
  if (spec.interval < 1) return false;
  if (spec.freq === 'weekly' && spec.byweekday.length === 0) return false;
  if (spec.freq === 'monthly' && spec.bymonthday.length === 0 && spec.nth_weekday === null) {
    return false;
  }
  if (spec.freq === 'yearly' && (spec.bymonth.length === 0 || spec.bymonthday.length === 0)) {
    return false;
  }
  if (spec.end.kind === 'on_date' && !spec.end.on_date) return false;
  if (spec.end.kind === 'after_count' && !spec.end.after_count) return false;
  return true;
}
