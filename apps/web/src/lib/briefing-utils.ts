/**
 * Briefing utilities — pure helpers shared across dashboard components.
 *
 * Strict no-dependencies on React or stateful modules → trivially unit-testable.
 */

import {
  ERROR_CODE_CONNECTOR_NETWORK,
  ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
  ERROR_CODE_CONNECTOR_RATE_LIMIT,
} from '@/types/briefing';
import type { CapabilityDirectiveWire } from '@/types/directive';
import { newIntentId } from '@/lib/intent-replay-guard';

// =============================================================================
// Relative time helper for "updated X ago" labels
// =============================================================================

/**
 * Compute a coarse "time ago" bucket for the given UTC ISO timestamp.
 *
 * Returns one of: 'just_now' | 'minutes' | 'hours' | 'days'
 * along with the integer count for interpolation in i18n strings.
 *
 * Buckets:
 *  - < 60 s   → just_now (count = 0)
 *  - < 60 min → minutes
 *  - < 24 h   → hours
 *  - else     → days
 */
export interface TimeAgoBucket {
  kind: 'just_now' | 'minutes' | 'hours' | 'days';
  count: number;
}

export function computeTimeAgo(generatedAtIso: string, now: Date = new Date()): TimeAgoBucket {
  const ts = new Date(generatedAtIso).getTime();
  if (Number.isNaN(ts)) return { kind: 'just_now', count: 0 };
  const deltaMs = Math.max(0, now.getTime() - ts);
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 60) return { kind: 'just_now', count: 0 };
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return { kind: 'minutes', count: minutes };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { kind: 'hours', count: hours };
  const days = Math.floor(hours / 24);
  return { kind: 'days', count: days };
}

/**
 * Bare relative-age label ("il y a 5 min") for D-04's freshness lines.
 *
 * Distinct from the UpdatedAtBadge keys on purpose: those embed the verb
 * ("mis à jour il y a…") while D-04 composes the age into larger sentences
 * ("Données d'il y a 5 min", "dernière tentative il y a 2 h"). Units are
 * abbreviations (min/h/j-equivalents), so no plural forms are needed.
 *
 * @param t - Translator (react-i18next `t`).
 * @param iso - ISO 8601 UTC timestamp.
 * @param now - Injectable clock for tests.
 */
export function timeAgoLabel(
  t: (key: string, options?: Record<string, unknown>) => string,
  iso: string,
  now: Date = new Date()
): string {
  const bucket = computeTimeAgo(iso, now);
  switch (bucket.kind) {
    case 'minutes':
      return t('dashboard.briefing.ago_minutes', { n: bucket.count });
    case 'hours':
      return t('dashboard.briefing.ago_hours', { n: bucket.count });
    case 'days':
      return t('dashboard.briefing.ago_days', { n: bucket.count });
    default:
      return t('dashboard.briefing.ago_just_now');
  }
}

/**
 * Absolute date (and time slot) for an item the reader may need to place.
 *
 * "il y a 4 j" answers *how long ago*; it never answers *when*. A meeting or a
 * message you are about to act on needs the second, so the CRM shows both —
 * the relative label to feel the distance, this one to pin it down.
 *
 * A SLOT renders both edges when the provider gave an end, because a meeting is
 * a span, not an instant. Nothing is invented: a missing end renders as a
 * single instant, and an all-day entry (midnight to midnight, provider-side)
 * renders without any clock at all rather than claiming "00:00".
 *
 * Rendered in the runtime's timezone through `Intl`, like every other absolute
 * time in this app — the backend always sends UTC ISO.
 *
 * @param locale - BCP-47 locale (the i18n language).
 * @param startIso - ISO 8601 UTC start.
 * @param endIso - ISO 8601 UTC end, when the source has one.
 * @returns The localized label, or null when nothing is parseable.
 */
export function dateTimeRangeLabel(
  locale: string,
  startIso: string | null,
  endIso: string | null = null
): string | null {
  if (!startIso) return null;
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return null;
  const end = endIso ? new Date(endIso) : null;
  const hasEnd = end !== null && !Number.isNaN(end.getTime());

  const date = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(start);

  // An all-day entry is midnight→midnight on the provider's side: printing
  // "00:00 – 00:00" would invent a precision the calendar never had.
  const clock = (value: Date) =>
    new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(value);
  const isMidnight = start.getHours() === 0 && start.getMinutes() === 0;
  const allDay = isMidnight && (!hasEnd || (end.getHours() === 0 && end.getMinutes() === 0));
  if (allDay) return date;

  // U+202F narrow no-break space around the dash: the range must never wrap
  // onto two lines on a 320 px screen.
  return hasEnd ? `${date}, ${clock(start)} – ${clock(end)}` : `${date}, ${clock(start)}`;
}

// =============================================================================
// Error code → i18n CTA key resolver
// =============================================================================

/**
 * Map a stable backend error_code to the localized CTA key (i18n).
 *
 * Returns null when no actionable CTA applies (e.g. internal errors).
 * Frontend cards use this to decide whether to render an inline "Reconnect" /
 * "Retry" button.
 */
/**
 * Build the chat deep-link a briefing item opens (QW-9).
 *
 * With a draft, the chat input is prefilled (never auto-sent) — the exact
 * onboarding `?draft=` pattern, generalized to the briefing cards.
 *
 * @param lng - Current URL locale segment.
 * @param draft - Optional prefill intent for the chat input.
 * @returns Localized chat route, with the encoded `draft` when provided.
 */
export function chatDraftHref(lng: string, draft?: string): string {
  const base = `/${lng}/dashboard/chat`;
  return draft ? `${base}?draft=${encodeURIComponent(draft)}` : base;
}

/**
 * Build the chat deep-link an IMMEDIATE action opens (QW-24, ADR-173).
 *
 * Unlike `?draft=` (prefill, the user presses Enter), `?intent=` is
 * AUTO-SENT by the chat page once it is safe to do so — the click on a
 * named action button IS the deliberate act. External writes stay behind
 * the pipeline's tool-level HITL cards.
 *
 * An optional `directive` rides alongside the prose (ADR-191): the sentence
 * stays what the user reads, the directive is what the backend guarantees to
 * run. Actions whose meaning is fully carried by their text pass nothing and
 * behave exactly as before.
 *
 * Every call also mints a one-shot `iid` (ADR-210): the URL is a replayable
 * carrier (browser history, omnibox, session restore), and the chat page
 * refuses to auto-send an iid it has already consumed. Fresh per CALL, so two
 * clicks on the same action remain two executions. Backend-emitted intent
 * links carry no iid and keep their click-is-consent semantics.
 *
 * @param lng - Current URL locale segment.
 * @param intent - The full localized request to send.
 * @param directive - Capability the click invoked, when the action has one.
 * @returns Localized chat route with the encoded `intent`.
 */
export function chatIntentHref(
  lng: string,
  intent: string,
  directive?: CapabilityDirectiveWire
): string {
  // `encodeURIComponent`, not `URLSearchParams`: the latter encodes a space as
  // `+`, which would rewrite every existing briefing deep link. Both decode
  // identically, but a change nobody asked for is a change nobody tested.
  const parts = [`intent=${encodeURIComponent(intent)}`];
  parts.push(`iid=${newIntentId()}`);
  if (directive) {
    parts.push(`capability=${encodeURIComponent(directive.capability)}`);
    parts.push(`subject=${encodeURIComponent(directive.subject)}`);
  }
  return `/${lng}/dashboard/chat?${parts.join('&')}`;
}

export function resolveErrorCtaKey(errorCode: string | null): string | null {
  switch (errorCode) {
    case ERROR_CODE_CONNECTOR_OAUTH_EXPIRED:
      return 'dashboard.briefing.actions.reconnect';
    case ERROR_CODE_CONNECTOR_NETWORK:
      return 'dashboard.briefing.actions.retry';
    case ERROR_CODE_CONNECTOR_RATE_LIMIT:
      return 'dashboard.briefing.actions.retry_later';
    default:
      return null;
  }
}

// =============================================================================
// Birthday display helper (parse '--MM-DD' or 'YYYY-MM-DD')
// =============================================================================

export interface ParsedBirthdayDate {
  month: number;
  day: number;
  /** Year is null when the user only stored MM-DD */
  year: number | null;
}

export function parseBirthdayIso(dateIso: string): ParsedBirthdayDate | null {
  const trimmed = dateIso.trim();
  // Partial: '--MM-DD'
  const partial = /^--(\d{2})-(\d{2})$/.exec(trimmed);
  if (partial) {
    return {
      month: Number(partial[1]),
      day: Number(partial[2]),
      year: null,
    };
  }
  // Full: 'YYYY-MM-DD'
  const full = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (full) {
    return {
      year: Number(full[1]),
      month: Number(full[2]),
      day: Number(full[3]),
    };
  }
  return null;
}

/**
 * Localize a contact-card date, year included only when the address book has one.
 *
 * A birthday stored without a year is the normal case, not a degraded one:
 * printing `1900` — or today's year — would state an age nobody wrote down.
 * Anything that is not one of the two ISO shapes is the provider's own free
 * text ("in the spring"), and is returned untouched rather than dropped.
 *
 * @param locale - BCP-47 locale (the i18n language).
 * @param value - `YYYY-MM-DD`, `--MM-DD`, or free text.
 * @returns The localized label, or the input when it is not a date.
 */
export function partialDateLabel(locale: string, value: string): string {
  const parsed = parseBirthdayIso(value);
  if (!parsed) return value;
  // Midday, never midnight: a timezone west of UTC would roll a midnight date
  // back to the previous day and move the birthday.
  const date = new Date(Date.UTC(parsed.year ?? 2000, parsed.month - 1, parsed.day, 12));
  try {
    return new Intl.DateTimeFormat(locale, {
      day: 'numeric',
      month: 'long',
      ...(parsed.year === null ? {} : { year: 'numeric' }),
    }).format(date);
  } catch {
    return value;
  }
}

// =============================================================================
// Number formatting (locale-aware, with thin-space thousands)
// =============================================================================

/**
 * Format an integer or float with the user's locale grouping.
 * Falls back to Intl with locale 'fr' default for the project's primary audience.
 */
export function formatNumberLocale(value: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(value);
  } catch {
    return String(value);
  }
}
