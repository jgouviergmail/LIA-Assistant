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

export function computeTimeAgo(
  generatedAtIso: string,
  now: Date = new Date(),
): TimeAgoBucket {
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
