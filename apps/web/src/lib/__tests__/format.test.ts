/**
 * Unit tests for the i18n number / currency / date / phone formatters.
 *
 * These wrap Intl and libphonenumber-js. Assertions normalize on the French
 * default locale (the project's primary audience) and pin the space-normalized
 * output (U+202F / U+00A0 → regular space) the module guarantees. Dates are
 * built with local-time component constructors so the assertions are timezone
 * independent.
 *
 * NOTE: `formatEuro`'s default `decimals` is 2 (its JSDoc still says 4 — a stale
 * doc, tracked separately); these tests assert the ACTUAL runtime behavior.
 */
import { describe, expect, it } from 'vitest';

import {
  formatCycleDates,
  formatDate,
  formatEuro,
  formatFileSize,
  formatNumber,
  formatPhone,
  formatPhonesInText,
  getCycleDates,
} from '../format';

describe('formatNumber', () => {
  it('groups thousands with the locale separator (spaces normalized for fr)', () => {
    expect(formatNumber(1234567)).toBe('1 234 567');
    expect(formatNumber(1234567, 'en')).toBe('1,234,567');
    expect(formatNumber(150)).toBe('150');
  });
});

describe('formatEuro', () => {
  it('defaults to 2 decimals (fr: symbol after)', () => {
    expect(formatEuro(0.0042)).toBe('0,00 €');
    expect(formatEuro(2.45, 2)).toBe('2,45 €');
  });

  it('honors an explicit decimals count', () => {
    expect(formatEuro(0.0042, 4)).toBe('0,0042 €');
  });

  it('places the symbol before the amount for en', () => {
    expect(formatEuro(2.45, 2, 'en')).toBe('€2.45');
  });
});

describe('formatFileSize', () => {
  it('escalates B → KB → MB', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1536)).toBe('1.5 KB');
    expect(formatFileSize(2_621_440)).toBe('2.5 MB');
  });
});

describe('formatDate', () => {
  it('formats with the locale short date by default', () => {
    expect(formatDate(new Date(2025, 9, 24))).toBe('24/10/2025');
    expect(formatDate(new Date(2025, 9, 24), 'en')).toBe('10/24/2025');
  });

  it('honors explicit Intl options', () => {
    expect(formatDate(new Date(2025, 9, 24), 'fr', { dateStyle: 'long' })).toContain('octobre');
  });

  it('accepts an ISO string', () => {
    expect(formatDate('2025-10-24T10:00:00.000Z', 'fr', { year: 'numeric' })).toBe('2025');
  });
});

describe('getCycleDates / formatCycleDates', () => {
  it('returns start and one-month-later end (day/month, 2-digit)', () => {
    expect(getCycleDates(new Date(2025, 9, 15))).toEqual({ start: '15/10', end: '15/11' });
    expect(getCycleDates(new Date(2025, 9, 15), 'en')).toEqual({ start: '10/15', end: '11/15' });
  });

  it('returns null for no date', () => {
    expect(getCycleDates(null)).toBeNull();
    expect(getCycleDates(undefined)).toBeNull();
  });

  it('formatCycleDates joins with a dash or returns "-"', () => {
    expect(formatCycleDates(new Date(2025, 9, 15))).toBe('15/10 - 15/11');
    expect(formatCycleDates(null)).toBe('-');
  });
});

describe('formatPhone', () => {
  it('formats a French number with dot separators', () => {
    expect(formatPhone('+33612345678')).toBe('06.12.34.56.78');
    expect(formatPhone('0612345678')).toBe('06.12.34.56.78');
  });

  it('uses the national format for other countries', () => {
    expect(formatPhone('+14155551234')).toContain('(415)');
  });

  it('returns the original input when not a valid number', () => {
    expect(formatPhone('notaphone')).toBe('notaphone');
    expect(formatPhone('')).toBe('');
    expect(formatPhone('   ')).toBe('   ');
    expect(formatPhone(null as unknown as string)).toBeNull();
  });
});

describe('formatPhonesInText', () => {
  it('rewrites phone numbers embedded in free text', () => {
    expect(formatPhonesInText('Call 0612345678 please')).toContain('06.12.34.56.78');
  });

  it('returns non-string / empty input unchanged', () => {
    expect(formatPhonesInText('')).toBe('');
    expect(formatPhonesInText(null as unknown as string)).toBeNull();
  });
});
