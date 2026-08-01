/**
 * Unit tests for the pure briefing helpers (no React, no stateful deps):
 * coarse "time ago" bucketing, connector error-code → CTA key resolution,
 * birthday ISO parsing (partial and full), and locale number formatting.
 */
import { describe, expect, it } from 'vitest';

import {
  chatIntentHref,
  computeTimeAgo,
  dateTimeRangeLabel,
  formatNumberLocale,
  parseBirthdayIso,
  partialDateLabel,
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

describe('partialDateLabel', () => {
  it('keeps the year missing when the address book has none', () => {
    // Printing a year nobody stored would state an age nobody wrote down.
    expect(partialDateLabel('fr', '--04-07')).toBe('7 avril');
    expect(partialDateLabel('en', '--04-07')).toBe('April 7');
  });

  it('shows the year when the address book stored one', () => {
    expect(partialDateLabel('fr', '1978-04-07')).toBe('7 avril 1978');
  });

  it('never rolls a date back a day west of UTC', () => {
    // Formatting at midnight would move a 1 January birthday to 31 December
    // for every reader in the Americas.
    expect(partialDateLabel('fr', '--01-01')).toBe('1 janvier');
    expect(partialDateLabel('fr', '2020-12-31')).toBe('31 décembre 2020');
  });

  it('passes through what is not a date', () => {
    // The provider lets one type anything into a birthday field.
    expect(partialDateLabel('fr', 'au printemps')).toBe('au printemps');
  });

  it('falls back to the raw value on an unusable locale', () => {
    expect(partialDateLabel('not a locale', '--04-07')).toBe('--04-07');
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

describe('dateTimeRangeLabel', () => {
  // "il y a 4 j" says how long ago; it never says WHEN. A meeting you are
  // about to act on needs the second.
  it('renders a slot with both edges', () => {
    const label = dateTimeRangeLabel('fr-FR', '2026-08-05T09:00:00Z', '2026-08-05T10:30:00Z');
    expect(label).toContain('2026');
    expect(label).toMatch(/\d{2}:\d{2} – \d{2}:\d{2}/);
  });

  it('renders a single instant when the source gave no end', () => {
    const label = dateTimeRangeLabel('fr-FR', '2026-08-05T09:00:00Z', null);
    expect(label).toMatch(/\d{2}:\d{2}$/);
    expect(label).not.toContain('–');
  });

  it('drops the clock entirely for an all-day entry', () => {
    // Midnight→midnight is how a provider encodes "all day". Printing
    // "00:00 – 00:00" would invent a precision the calendar never had.
    const label = dateTimeRangeLabel('fr-FR', '2026-08-01T00:00:00', '2026-08-03T00:00:00');
    expect(label).not.toMatch(/\d{2}:\d{2}/);
  });

  it('answers null rather than a broken string', () => {
    expect(dateTimeRangeLabel('fr-FR', null)).toBeNull();
    expect(dateTimeRangeLabel('fr-FR', 'pas une date')).toBeNull();
  });

  it('ignores an unparseable END rather than losing the start', () => {
    const label = dateTimeRangeLabel('fr-FR', '2026-08-05T09:00:00Z', 'boom');
    expect(label).not.toBeNull();
    expect(label).not.toContain('–');
  });

  it('follows the locale', () => {
    const fr = dateTimeRangeLabel('fr-FR', '2026-08-05T09:00:00Z');
    const en = dateTimeRangeLabel('en-US', '2026-08-05T09:00:00Z');
    expect(fr).not.toBe(en);
  });
});

describe('chatIntentHref', () => {
  it('keeps the historical shape when no capability is invoked', () => {
    // Every briefing card builds its link this way, so the no-directive output
    // must stay byte-identical. URLSearchParams would have encoded the spaces
    // as `+` and quietly rewritten every existing deep link.
    expect(chatIntentHref('fr', 'Résume mes mails')).toBe(
      '/fr/dashboard/chat?intent=R%C3%A9sume%20mes%20mails'
    );
  });

  it('carries the capability and its subject (ADR-191)', () => {
    const href = chatIntentHref('fr', 'Point 360° sur Paul Martin', {
      capability: 'person_overview',
      subject: 'Paul Martin',
    });
    const query = new URLSearchParams(href.split('?')[1]);

    expect(query.get('intent')).toBe('Point 360° sur Paul Martin');
    expect(query.get('capability')).toBe('person_overview');
    expect(query.get('subject')).toBe('Paul Martin');
  });

  it('survives a name the URL would otherwise mangle', () => {
    const href = chatIntentHref('de', 'Punkt', {
      capability: 'person_overview',
      subject: 'Anaïs Müller & Co',
    });

    expect(new URLSearchParams(href.split('?')[1]).get('subject')).toBe('Anaïs Müller & Co');
  });
});
