/**
 * Unit tests for the pure briefing helpers (no React, no stateful deps):
 * coarse "time ago" bucketing, connector error-code → CTA key resolution,
 * birthday ISO parsing (partial and full), and locale number formatting.
 */
import { describe, expect, it } from 'vitest';

import {
  computeTimeAgo,
  formatNumberLocale,
  parseBirthdayIso,
  resolveErrorCtaKey,
} from '../briefing-utils';
import {
  ERROR_CODE_CONNECTOR_NETWORK,
  ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
  ERROR_CODE_CONNECTOR_RATE_LIMIT,
} from '@/types/briefing';

describe('computeTimeAgo', () => {
  const now = new Date('2025-01-15T12:00:00.000Z');

  it('returns just_now for an unparseable timestamp', () => {
    expect(computeTimeAgo('not-a-date', now)).toEqual({ kind: 'just_now', count: 0 });
  });

  it('buckets sub-minute deltas as just_now', () => {
    expect(computeTimeAgo('2025-01-15T11:59:30.000Z', now)).toEqual({ kind: 'just_now', count: 0 });
  });

  it('buckets minutes / hours / days', () => {
    expect(computeTimeAgo('2025-01-15T11:45:00.000Z', now)).toEqual({ kind: 'minutes', count: 15 });
    expect(computeTimeAgo('2025-01-15T09:00:00.000Z', now)).toEqual({ kind: 'hours', count: 3 });
    expect(computeTimeAgo('2025-01-12T12:00:00.000Z', now)).toEqual({ kind: 'days', count: 3 });
  });

  it('clamps a future timestamp to just_now (no negative delta)', () => {
    expect(computeTimeAgo('2025-01-15T12:05:00.000Z', now)).toEqual({ kind: 'just_now', count: 0 });
  });
});

describe('resolveErrorCtaKey', () => {
  it('maps actionable connector errors to CTA keys', () => {
    expect(resolveErrorCtaKey(ERROR_CODE_CONNECTOR_OAUTH_EXPIRED)).toBe(
      'dashboard.briefing.actions.reconnect'
    );
    expect(resolveErrorCtaKey(ERROR_CODE_CONNECTOR_NETWORK)).toBe(
      'dashboard.briefing.actions.retry'
    );
    expect(resolveErrorCtaKey(ERROR_CODE_CONNECTOR_RATE_LIMIT)).toBe(
      'dashboard.briefing.actions.retry_later'
    );
  });

  it('returns null for non-actionable / unknown / null codes', () => {
    expect(resolveErrorCtaKey('SOME_INTERNAL_ERROR')).toBeNull();
    expect(resolveErrorCtaKey(null)).toBeNull();
  });
});

describe('parseBirthdayIso', () => {
  it('parses the partial --MM-DD form (year null)', () => {
    expect(parseBirthdayIso('--12-25')).toEqual({ month: 12, day: 25, year: null });
  });

  it('parses the full YYYY-MM-DD form', () => {
    expect(parseBirthdayIso('1990-07-14')).toEqual({ year: 1990, month: 7, day: 14 });
  });

  it('trims surrounding whitespace', () => {
    expect(parseBirthdayIso('  --01-01  ')).toEqual({ month: 1, day: 1, year: null });
  });

  it('returns null for an unrecognized shape', () => {
    expect(parseBirthdayIso('14/07/1990')).toBeNull();
    expect(parseBirthdayIso('')).toBeNull();
  });
});

describe('formatNumberLocale', () => {
  it('formats with the given locale', () => {
    expect(formatNumberLocale(1234567, 'en')).toBe('1,234,567');
  });

  it('falls back to String() when the locale is invalid', () => {
    expect(formatNumberLocale(42, '123')).toBe('42');
  });
});
