/**
 * The words of the ntfy settings for what the API says in codes (ADR-391).
 *
 * The API names an outcome (`NtfyOutcome`) or a refusal (`ntfy_*`) and never translates it:
 * this module is the one place that turns a code into a locale key. A code this build does not
 * know (an API newer than the page) reads as the generic sentence, never as a raw key.
 * `apps/api/tests/unit/domains/notifications/test_ntfy_web_vocabulary.py` holds both lists equal
 * to the API's.
 */

import type { NtfyOutcome } from '@/hooks/useNtfySubscriptions';

/** Every outcome the API can report, in the order the API declares them. */
export const NTFY_OUTCOMES = [
  'sent',
  'auth_refused',
  'not_found',
  'too_large',
  'rate_limited',
  'refused',
  'server_error',
  'unreachable',
  'no_answer',
  'url_refused',
  'not_configured',
] as const satisfies readonly NtfyOutcome[];

/** Every refusal code the ntfy settings can receive. */
export const NTFY_REFUSALS = [
  'ntfy_instance_unavailable',
  'ntfy_custom_servers_disabled',
  'ntfy_server_url_not_https',
  'ntfy_server_url_invalid',
  'ntfy_server_url_refused',
  'ntfy_topic_invalid',
  'ntfy_token_invalid',
  'ntfy_subscription_limit',
  'ntfy_subscription_unreadable',
] as const;

export type NtfyRefusal = (typeof NTFY_REFUSALS)[number];

const PREFIX = 'settings.notifications.ntfy';
const KNOWN_REFUSALS: ReadonlySet<string> = new Set(NTFY_REFUSALS);
const KNOWN_OUTCOMES: ReadonlySet<string> = new Set(NTFY_OUTCOMES);

/** The key of what a publication's outcome means to the person. */
export function outcomeKey(outcome: string): string {
  return KNOWN_OUTCOMES.has(outcome) ? `${PREFIX}.outcome.${outcome}` : `${PREFIX}.outcome.unknown`;
}

/** The key of why the settings refused a change; the generic sentence for an unknown code. */
export function refusalKey(code: string | null): string {
  return code !== null && KNOWN_REFUSALS.has(code)
    ? `${PREFIX}.refusal.${code}`
    : `${PREFIX}.refusal.unknown`;
}
