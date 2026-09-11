/**
 * Compose a mail watch from a briefing card (ADR-281, lot 5).
 *
 * A « watch » is a CONDITION routine on a `mail_match`: « tell me when Marie
 * replies ». The chat cannot author one — `create_scheduled_action_tool`
 * deliberately creates `time` routines only, and growing its signature to
 * author conditions in natural language is a design of its own, deferred in
 * writing — so the shortcut goes through `POST /scheduled-actions`, the same
 * door the routine studio uses.
 *
 * The SHAPE lives here, in one place, rather than inside the card: the studio
 * form already composes a routine, and a second composer scattered through a
 * component is how the two would come to disagree about what a watch is.
 *
 * Three decisions the shape rests on:
 *
 * - **the sender is the query, never the subject.** A subject drifts through
 *   `Re:` and `Fwd:` and is often shared by unrelated threads, while the
 *   address is the stable identity of who one is waiting for. It falls back to
 *   the display name only when no address came through.
 * - **the end is the recurrence's own `SeriesEnd`.** The engine already ends a
 *   series, publishes it, edits it in the studio and tells it in six
 *   languages; a second field for « until when » would be a second authority.
 * - **the cadence is a safety net, not the mechanism.** The push wake serves a
 *   matching mail within a couple of minutes; these two daily evaluations are
 *   what still answers on an account with no push channel configured.
 */

import type { ConditionConfig, RecurrenceSpec } from '@/hooks/useScheduledActions';

/** How long a watch lives before its series ends, in days. */
export const MAIL_WATCH_DAYS = 14;

/** The fallback evaluations of a served day, in the account's own zone. */
export const MAIL_WATCH_HOURS = [9, 17] as const;

/** The longest query `ConditionConfig` accepts (mirrors the backend bound). */
export const MAIL_WATCH_QUERY_MAX = 120;

/** The shortest one it accepts — below this the API answers 422. */
export const MAIL_WATCH_QUERY_MIN = 2;

/** What the card knows about the mail being watched. */
export interface MailWatchSource {
  sender_email: string | null;
  sender_name: string | null;
}

/** The payload `POST /scheduled-actions` expects for a watch. */
export interface MailWatchPayload {
  title: string;
  action_prompt: string;
  recurrence: RecurrenceSpec;
  trigger_kind: 'condition';
  condition_config: ConditionConfig;
}

/**
 * The stable identity of who is being awaited.
 *
 * @param mail - The card's own fields.
 * @returns The address, else the display name, else an empty string.
 */
export function watchQueryFor(mail: MailWatchSource): string {
  const candidate = (mail.sender_email || mail.sender_name || '').trim();
  return candidate.slice(0, MAIL_WATCH_QUERY_MAX);
}

/**
 * Whether a watch can be offered for this mail at all.
 *
 * A mail whose sender came through as neither an address nor a name gives
 * nothing to watch FOR, and the API would refuse the payload. Offering a
 * button that always fails is worse than offering none.
 *
 * @param mail - The card's own fields.
 * @returns True when a watch would be accepted.
 */
export function canWatch(mail: MailWatchSource): boolean {
  return watchQueryFor(mail).length >= MAIL_WATCH_QUERY_MIN;
}

/**
 * The local date the series ends on, `YYYY-MM-DD`.
 *
 * Built from the local calendar fields rather than from `toISOString()`, which
 * converts to UTC first: on the evening of the 14th in Paris that would name
 * the 15th, ending the series a day early for half of every day.
 *
 * @param from - The day to count from.
 * @param days - How many days the watch lives.
 * @returns The last local day, included.
 */
export function watchEndDate(from: Date, days: number = MAIL_WATCH_DAYS): string {
  const end = new Date(from.getFullYear(), from.getMonth(), from.getDate() + days);
  const month = `${end.getMonth() + 1}`.padStart(2, '0');
  const day = `${end.getDate()}`.padStart(2, '0');
  return `${end.getFullYear()}-${month}-${day}`;
}

/**
 * Build the routine a « Watch » chip posts.
 *
 * @param input - The mail, the translated wording, and the day to count from.
 * @returns The create payload, ready for `POST /scheduled-actions`.
 * @throws Error when the mail carries no watchable sender — callers guard with
 *   {@link canWatch}, and throwing beats posting something the API refuses.
 */
export function buildMailWatch(input: {
  mail: MailWatchSource;
  title: string;
  actionPrompt: string;
  now?: Date;
}): MailWatchPayload {
  const query = watchQueryFor(input.mail);
  if (query.length < MAIL_WATCH_QUERY_MIN) {
    throw new Error('mail_watch_without_sender');
  }
  const from = input.now ?? new Date();
  const anchor = watchEndDate(from, 0);
  return {
    title: input.title,
    action_prompt: input.actionPrompt,
    recurrence: {
      freq: 'daily',
      interval: 1,
      anchor_date: anchor,
      times: {
        mode: 'at',
        at: MAIL_WATCH_HOURS.map(hour => ({ hour, minute: 0 })),
      },
      byweekday: [],
      bymonthday: [],
      nth_weekday: null,
      bymonth: [],
      end: { kind: 'on_date', on_date: watchEndDate(from) },
    },
    trigger_kind: 'condition',
    condition_config: { type: 'mail_match', query },
  };
}

/**
 * The little a routine must expose to be recognised as a watch.
 *
 * Declared structurally rather than as the whole `ScheduledAction`: this is
 * every field the answer depends on, so a caller (and a test) may hand over
 * exactly that without casting a partial object into a twenty-field type.
 */
export interface WatchCandidate {
  is_enabled: boolean;
  trigger_kind: string;
  condition_config: ConditionConfig | null;
}

/**
 * An existing routine already watching for the same thing, if there is one.
 *
 * Clicking the chip on two mails from the same person would otherwise create
 * two identical watches, each consuming one of the account's twenty routine
 * slots and each notifying — so one awaited reply would be announced twice.
 * That is precisely the irritation the proactive programme exists to avoid,
 * which is why the chip asks before it writes.
 *
 * Only ENABLED routines count: one the person paused is a decision to stop
 * being told, and one closed at the end of its series is over. Either way,
 * arming a fresh watch is the right answer rather than reviving that row.
 *
 * @param routines - What the account already holds.
 * @param query - Who the new watch would wait for.
 * @returns The routine already waiting for them, else undefined.
 */
export function existingWatchFor<T extends WatchCandidate>(
  routines: readonly T[],
  query: string
): T | undefined {
  const needle = query.trim().toLowerCase();
  if (!needle) return undefined;
  return routines.find(
    routine =>
      routine.is_enabled &&
      routine.trigger_kind === 'condition' &&
      routine.condition_config?.type === 'mail_match' &&
      (routine.condition_config.query ?? '').trim().toLowerCase() === needle
  );
}
