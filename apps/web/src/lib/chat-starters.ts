/**
 * Starters for the empty chat (W8) — the first screen stops being a dead end.
 *
 * ## Why these three, and not the twelve the onboarding already ships
 *
 * The onboarding carries 12 categories of examples ("quels sont mes 2 derniers
 * emails ?", "affiche mes rendez-vous"…), all translated. Reusing them here
 * would be the obvious move and the wrong one: on an empty chat we have no idea
 * whether the account has a mail, calendar or tasks connector, and the chat page
 * deliberately does not fetch `/connectors`. Offering "show my last emails" to
 * someone with no mail connector turns the very first interaction into a
 * failure.
 *
 * So the starters are restricted to intents that ALWAYS resolve, whatever the
 * account state:
 *  - `capabilities` — LIA introduces herself; pure model, no data source;
 *  - `reminder`     — reminders live in local tables (`fetch_reminders` never
 *                     raises `ConnectorNotConfiguredError`);
 *  - `explain`      — a pure generation task.
 *
 * Everything else stays one click away through the FAQ, whose ~375 authored
 * examples became actionable in W1 — richness without a broken promise.
 *
 * A starter PREFILLS the composer and never sends, exactly like the follow-up
 * chips it shares its rail with: the user reads the phrase, edits it, decides.
 */

/** Identifiers of the starters, in display order. */
export const CHAT_STARTER_IDS = ['capabilities', 'reminder', 'explain'] as const;

export type ChatStarterId = (typeof CHAT_STARTER_IDS)[number];

/** i18n key holding the phrase a starter drops into the composer. */
export function starterTextKey(id: ChatStarterId): string {
  return `chat.starters.${id}`;
}

/**
 * Grounded suggestion ids this build can word.
 *
 * The backend contract is a plain string, so a new kind can ship server-first.
 * `t()` answers an unknown key with the key itself — and this rail does not
 * merely display its text, it DROPS IT INTO THE COMPOSER: the reader would
 * send `chat.suggestions.new_thing` to the assistant. An id we cannot word is
 * therefore skipped, and a generic starter takes its place.
 */
export const KNOWN_SUGGESTION_IDS: ReadonlySet<string> = new Set([
  'next_event',
  'important_mails',
  'close_loop',
  // The only source a connector-less account can feed: reminders live in a
  // local table. Without it the rail was generic for every such account.
  'reminder',
]);

/** A rail entry: a stable key and the phrase it drops into the composer. */
export interface StarterRailEntry {
  key: string;
  text: string;
  /** True when the phrase names something real from the reader's day. */
  grounded: boolean;
}

/**
 * The rail the empty chat shows: what LIA actually knows first, then the
 * generic ways in.
 *
 * **Grounded suggestions come first and generics FILL UP.** Showing only one
 * grounded entry would impoverish the screen a newcomer lands on, and showing
 * six would turn a nudge into a menu. Three, always — the count the generic
 * rail already had.
 *
 * **Generics can never be exhausted by a grounded duplicate**: the two sets
 * are disjoint by construction (a grounded id names an event, a mail batch or
 * a commitment; a starter id names a capability, a reminder or an
 * explanation), so no de-duplication is needed and none is faked.
 *
 * @param grounded - Suggestions the server could back with cached evidence.
 * @param t - Translator; grounded wording is resolved from `chat.suggestions.*`.
 * @returns Exactly `CHAT_STARTER_IDS.length` entries, grounded ones first.
 */
export function composeStarterRail(
  grounded: readonly { id: string; params?: Record<string, string> }[],
  t: (key: string, options?: Record<string, unknown>) => string
): StarterRailEntry[] {
  const entries: StarterRailEntry[] = grounded
    .filter(suggestion => KNOWN_SUGGESTION_IDS.has(suggestion.id))
    .map(suggestion => ({
      key: `grounded:${suggestion.id}`,
      text: t(`chat.suggestions.${suggestion.id}`, suggestion.params),
      grounded: true,
    }));

  for (const id of CHAT_STARTER_IDS) {
    if (entries.length >= CHAT_STARTER_IDS.length) break;
    entries.push({ key: `starter:${id}`, text: t(starterTextKey(id)), grounded: false });
  }

  return entries.slice(0, CHAT_STARTER_IDS.length);
}
