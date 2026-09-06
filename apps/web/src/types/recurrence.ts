/**
 * The recurrence vocabulary, shared by every consumer.
 *
 * These types lived in `hooks/useScheduledActions.ts` while routines were the
 * only consumer, and `lib/recurrence.ts` plus the five editor components read
 * them from there — the generic layer importing its shape from ONE of its
 * users. Invisible with a single consumer; the reminders lot made it a
 * settings screen describing a reminder in the routines' vocabulary.
 *
 * The shapes mirror `src/core/recurrence/spec.py`; the backend contract guard
 * (`tests/unit/api/test_frontend_contract_guard.py`) compares them field by
 * field, in both directions.
 */

/** How a recurrence walks the calendar. `once` is a recurrence of one. */
export type RecurrenceFreq = 'once' | 'daily' | 'weekly' | 'monthly' | 'yearly';

/** A wall-clock moment inside a day, in the routine's own timezone. */
export interface TimeOfDay {
  hour: number;
  minute: number;
}

/**
 * The moments a served day fires at: explicit, or a step between two bounds.
 *
 * The browser NEVER expands a `mode: 'every'` step for display — the server
 * publishes the result in `times_of_day`. Expanding it here would be a second
 * reading of the schedule, and the two would disagree at the daylight-saving
 * edges. The editor previews a step while the reader is still choosing it;
 * that preview is never what a saved routine renders from.
 */
export interface DailyTimes {
  mode: 'at' | 'every';
  at?: TimeOfDay[];
  step_minutes?: number | null;
  start?: TimeOfDay | null;
  end?: TimeOfDay | null;
}

/** When a series stops: never, on a local date, or after N occurrences. */
export interface SeriesEnd {
  kind: 'never' | 'on_date' | 'after_count';
  /** `YYYY-MM-DD`, the LAST local day, included. */
  on_date?: string | null;
  /** How many INSTANTS, not days. */
  after_count?: number | null;
}

/**
 * A recurrence: which calendar days, and which moments inside them.
 *
 * `anchor_date` is BOTH the day the series starts and the phase of an
 * interval — without it, "every 3 days" resolves to "in 3 days" on every
 * computation (measured server-side, 2026-09-06).
 */
export interface RecurrenceSpec {
  freq: RecurrenceFreq;
  times: DailyTimes;
  /** `YYYY-MM-DD`. */
  anchor_date: string;
  interval: number;
  /** ISO weekdays, 1 = Monday … 7 = Sunday (weekly). */
  byweekday: number[];
  /** 1..31, or -1 for the last day (monthly / yearly). */
  bymonthday: number[];
  /** `[nth, ISO weekday]`, nth in -1 or 1..5 (monthly). */
  nth_weekday: [number, number] | null;
  /** 1..12 (yearly). */
  bymonth: number[];
  end: SeriesEnd;
}
