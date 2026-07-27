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
