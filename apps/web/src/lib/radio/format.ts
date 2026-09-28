/**
 * What the radio's surfaces say, computed apart from the components (ADR-324):
 * the cost so far and what the planned listening will cost, the minutes left
 * before the automatic stop, the line being spoken. Pure, so the wording is
 * tested without React.
 */
import type { Language } from '@/i18n/settings';
import { formatDate, formatEuro } from '@/lib/format';

import type { RadioView } from './controller';
import { BUDGET_REACHED } from './errors';
import type { RadioSegment } from './types';

/** Decimals of a live cost: a session spends fractions of a cent per programme. */
const COST_DECIMALS = 4;

/** The cost so far in the listener's locale, or null while the API does not know it. */
export function radioCost(costEur: number | null, locale: Language): string | null {
  return costEur === null ? null : formatEuro(costEur, COST_DECIMALS, locale);
}

/**
 * The programme airing — played, or held on a pause — else null: between two
 * programmes, while tuning in or signing off, and once the session is over.
 */
export function airingSegment(view: RadioView): RadioSegment | null {
  if (view.status !== 'playing' && view.status !== 'paused') return null;
  return view.current;
}

/** The most decimals an estimate spends on an amount too small to round. */
const ESTIMATE_DECIMALS_MAX = 4;

/**
 * An estimate in the listener's locale, with two significant digits: it is a
 * guess, and « 0,051 € » says so where « 0,0512 € » would claim a precision
 * nobody has.
 */
export function radioCostEstimate(eur: number, locale: Language): string {
  if (eur <= 0) return formatEuro(0, 2, locale);
  // The decimals follow the ROUNDED amount: 0.0995 rounds to 0.10, not 0.100.
  const rounded = Number(eur.toPrecision(2));
  const decimals = Math.min(
    ESTIMATE_DECIMALS_MAX,
    Math.max(0, 1 - Math.floor(Math.log10(rounded)))
  );
  return formatEuro(rounded, decimals, locale);
}

/**
 * What the planned listening will cost: the timer's minutes, or an hour when
 * no timer stops the station; null before the API has an estimate, or once the
 * station is off.
 */
export function radioEstimateMessage(view: RadioView, locale: Language): RadioMessage | null {
  if (view.status === 'ended' || view.status === 'idle') return null;
  if (view.costEstimateEur === null || view.costEstimateS === null) return null;
  const cost = radioCostEstimate(view.costEstimateEur, locale);
  if (view.stopAt === null) return { key: 'radio.banner.estimate_hourly', values: { cost } };
  return {
    key: 'radio.banner.estimate',
    values: { cost, minutes: Math.round(view.costEstimateS / 60) },
  };
}

/**
 * Whole minutes left before the automatic stop, rounded up (a session with
 * twenty seconds left has « 1 min » left, never « 0 »); null without a timer
 * or for an instant the browser cannot read, 0 once it has passed.
 */
export function minutesLeft(stopAt: string | null, nowMs: number): number | null {
  if (stopAt === null) return null;
  const left = Date.parse(stopAt) - nowMs;
  if (Number.isNaN(left)) return null;
  return left <= 0 ? 0 : Math.ceil(left / 60_000);
}

/**
 * The line being spoken at `positionS`: the last one that has started, or -1
 * before the first (the music of the introduction).
 */
export function currentLineIndex(offsets: readonly number[], positionS: number): number {
  let current = -1;
  offsets.forEach((offset, index) => {
    if (offset <= positionS) current = index;
  });
  return current;
}

/**
 * A source's link, only when it is a web address: the sources come from feeds
 * strangers publish, and a `javascript:` or `data:` link must never become an
 * anchor on the page.
 */
export function webUrl(url: string | null): string | null {
  if (url === null) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
  } catch {
    return null;
  }
}

/** Why a session ended, as the API names it — anything else reads as « other ». */
const END_REASONS: ReadonlySet<string> = new Set([
  'timer',
  'listener',
  'idle',
  'failures',
  'budget',
]);

/** A translation key and its values. */
export interface RadioMessage {
  key: string;
  values?: Record<string, number | string>;
}

/** How an instant the radio names reads: the day, and the time on the listener's clock. */
const RADIO_INSTANT: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  hour: '2-digit',
  minute: '2-digit',
};

/** A euro amount the radio's budget quotes: to the cent, in the listener's locale. */
export function radioBudgetAmount(eur: number, locale: Language): string {
  return formatEuro(eur, 2, locale);
}

/** An instant the radio's budget names (when it lifts), in the listener's locale. */
export function radioBudgetInstant(iso: string, locale: Language): string {
  return formatDate(iso, locale, RADIO_INSTANT);
}

/**
 * What the player says about the station: the error first — a start refused at
 * the listener's budget quotes it, and when it lifts — then why it ended, then
 * how long the first voice should take, then the state itself.
 */
export function radioStatusMessage(view: RadioView, locale: Language): RadioMessage {
  if (view.error === BUDGET_REACHED) {
    const budget = view.refusedBudget;
    // Never a sentence quoting figures nobody sent.
    if (budget === null) return { key: 'radio.errors.start_failed' };
    return {
      key: `radio.errors.${BUDGET_REACHED}`,
      values: {
        max: radioBudgetAmount(budget.maxEur, locale),
        lifts: radioBudgetInstant(budget.liftsAt, locale),
      },
    };
  }
  if (view.error !== null) return { key: `radio.errors.${view.error}` };
  if (view.status === 'ended') {
    const reason =
      view.endReason !== null && END_REASONS.has(view.endReason) ? view.endReason : 'other';
    return { key: `radio.end_reason.${reason}` };
  }
  if (view.status === 'starting' && view.startupEstimateS !== null) {
    return {
      key: 'radio.banner.starting_eta',
      values: { seconds: Math.max(1, Math.round(view.startupEstimateS)) },
    };
  }
  return { key: `radio.banner.${view.status}` };
}
