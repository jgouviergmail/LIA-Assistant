/**
 * The refusals the radio's API names (`detail.code`), as the sentence to show (ADR-324).
 *
 * Every code the API sends has a sentence in the six languages (a backend
 * guard pins the pair): the start refusals, the settings a write refuses, the
 * site limit with its maximum, and a site with no feed by what looking for it
 * found. A bound the API enforces travels beside its code and is quoted as is —
 * a start past the listener's radio budget quotes the bound and when it lifts.
 */
import type { TFunction } from 'i18next';

import { getApiErrorFields, getApiErrorStatus } from '@/lib/api-error';

import type { RadioDiscoveryOutcome } from './types';

/** A refusal, as the sentence the reader is shown. */
export interface RadioRefusal {
  /** The i18n key of its sentence. */
  key: string;
  /** Its interpolation values: the bound the API published beside the code. */
  values?: Record<string, number>;
}

/** What a radio write answered: done, or refused (with its sentence when the API named it). */
export type RadioWrite<T> = { ok: true; value: T } | { ok: false; refusal: RadioRefusal | null };

/** The refusals a start answers with — the player's banner tells them. */
export const RADIO_START_REFUSALS = [
  'radio_instance_full',
  'radio_no_voice',
  'radio_voice_unavailable',
  'radio_budget_reached',
] as const;

export type RadioStartRefusal = (typeof RADIO_START_REFUSALS)[number];

/** The start refusal that quotes the listener's radio budget (ADR-324 decision 37). */
export const BUDGET_REACHED: RadioStartRefusal = 'radio_budget_reached';

/** What a start past the listener's radio budget quotes beside its code. */
export interface RadioBudgetRefusal {
  /** The bound over the rolling day, in euros. */
  maxEur: number;
  /** When enough of the spend leaves the window to play again (ISO 8601). */
  liftsAt: string;
}

/** A start the API refused: its reason, and the budget it quotes when that is the reason. */
export interface RadioStartRefused {
  code: RadioStartRefusal;
  budget: RadioBudgetRefusal | null;
}

/**
 * Told in their own words, with nothing beside the code. The budget is not:
 * only a start meets it, and its sentence quotes figures (`startRefusalOf`).
 */
const PLAIN: ReadonlySet<string> = new Set<string>([
  ...RADIO_START_REFUSALS.filter(code => code !== BUDGET_REACHED),
  'radio_voice_unknown',
  'radio_personality_unknown',
]);

/** What looking for a site's feed found when it found none (a sentence each). */
const NOT_FOUND: ReadonlySet<string> = new Set<Exclude<RadioDiscoveryOutcome, 'found'>>([
  'not_public',
  'unreachable',
  'forbidden',
  'no_feed',
]);

/** The refusals that quote a bound, and the name their sentence gives it. */
const BOUNDED: Readonly<Record<string, { field: string; value: string }>> = {
  radio_timer_too_long: { field: 'max_minutes', value: 'max' },
  radio_source_limit: { field: 'max_sources', value: 'count' },
};

/**
 * Whether a code is one of the start refusals.
 *
 * @param code - A refusal's `detail.code`, when it has one.
 */
export function isStartRefusal(code: string | undefined): code is RadioStartRefusal {
  return (RADIO_START_REFUSALS as readonly string[]).includes(code ?? '');
}

/**
 * Why a start was refused, with the budget its sentence quotes.
 *
 * @param error - Anything the start's `catch` block received.
 * @returns The refusal; `null` for anything else — and for a budget refusal
 *   that did not send its bound and its instant, since a sentence quoting
 *   figures nobody sent would be a claim nobody made (the caller then says its
 *   own generic sentence).
 */
export function startRefusalOf(error: unknown): RadioStartRefused | null {
  const fields = getApiErrorFields(error);
  const code = fields?.code;
  if (!fields || typeof code !== 'string' || !isStartRefusal(code)) return null;
  if (code !== BUDGET_REACHED) return { code, budget: null };
  const { max_eur: maxEur, lifts_at: liftsAt } = fields;
  return typeof maxEur === 'number' && typeof liftsAt === 'string'
    ? { code, budget: { maxEur, liftsAt } }
    : null;
}

/**
 * The sentence of a refusal the radio's API named.
 *
 * @param error - Anything a `catch` block received.
 * @returns The refusal's sentence, or `null` when the API named none (the
 *   caller says its own generic sentence).
 */
export function radioRefusalOf(error: unknown): RadioRefusal | null {
  const fields = getApiErrorFields(error);
  const code = fields?.code;
  if (!fields || typeof code !== 'string') return null;
  if (PLAIN.has(code)) return { key: `radio.errors.${code}` };
  const bounded = BOUNDED[code];
  if (bounded) {
    const bound = fields[bounded.field];
    return typeof bound === 'number'
      ? { key: `radio.errors.${code}`, values: { [bounded.value]: bound } }
      : null;
  }
  if (code === 'radio_source_refused' && typeof fields.outcome === 'string') {
    return NOT_FOUND.has(fields.outcome)
      ? { key: `radio.settings.sites.outcome.${fields.outcome}` }
      : null;
  }
  return null;
}

/** A site lookup has its own rate limit, shared by checks and additions. */
export function sourceLookupRefusalOf(error: unknown): RadioRefusal | null {
  if (getApiErrorStatus(error) === 429) {
    return { key: 'radio.settings.sites.rate_limited' };
  }
  return radioRefusalOf(error);
}

/**
 * The sentence to show for a refused write.
 *
 * @param t - The translator.
 * @param refusal - The refusal the API named, when it named one.
 * @param fallbackKey - The caller's own sentence when it did not.
 */
export function sayRefusal(
  t: TFunction,
  refusal: RadioRefusal | null,
  fallbackKey: string
): string {
  return refusal ? t(refusal.key, refusal.values) : t(fallbackKey);
}
