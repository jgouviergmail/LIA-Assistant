/**
 * Unit tests for the browser timezone utilities (Intl-based).
 *
 * Time-sensitive helpers run under fake timers pinned to a fixed winter instant
 * so DST-dependent offsets (Europe/Paris = UTC+1 in January) are deterministic.
 * `getBrowserTimezone` is exercised by stubbing `Intl.DateTimeFormat`'s
 * resolvedOptions; the logger is mocked so error paths stay silent.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  formatTimezoneDisplay,
  getBrowserTimezone,
  getCurrentTimeInTimezone,
  getGreetingPeriod,
  getTimezoneOffset,
  groupTimezonesByRegion,
} from '../timezone';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

describe('getBrowserTimezone', () => {
  afterEach(() => vi.restoreAllMocks());

  function stubResolvedTimeZone(timeZone: string): void {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockReturnValue({
      timeZone,
      locale: 'en-US',
      calendar: 'gregory',
      numberingSystem: 'latn',
    } as Intl.ResolvedDateTimeFormatOptions);
  }

  it('returns a well-formed IANA zone', () => {
    stubResolvedTimeZone('Europe/Paris');
    expect(getBrowserTimezone()).toBe('Europe/Paris');
  });

  it('returns null when the zone has no region separator', () => {
    stubResolvedTimeZone('UTC');
    expect(getBrowserTimezone()).toBeNull();
  });

  it('returns null and logs when detection throws', () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, 'resolvedOptions').mockImplementation(() => {
      throw new Error('boom');
    });
    expect(getBrowserTimezone()).toBeNull();
  });
});

describe('time-dependent helpers (fixed winter instant)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-01-15T12:00:00.000Z'));
  });
  afterEach(() => vi.useRealTimers());

  describe('getTimezoneOffset', () => {
    it('returns UTC+1 for Paris in January', () => {
      expect(getTimezoneOffset('Europe/Paris')).toBe('UTC+1');
    });

    it('returns a UTC-prefixed offset for UTC itself', () => {
      expect(getTimezoneOffset('UTC')).toContain('UTC');
    });

    it('falls back to UTC for an invalid zone (catch branch)', () => {
      expect(getTimezoneOffset('Invalid/Zone')).toBe('UTC');
    });
  });

  describe('getCurrentTimeInTimezone', () => {
    it('formats the current instant for a valid zone', () => {
      expect(getCurrentTimeInTimezone('Europe/Paris', 'fr-FR')).toContain('2025');
    });

    it('falls back to toLocaleString for an empty zone', () => {
      expect(getCurrentTimeInTimezone('', 'fr-FR')).toBeTruthy();
    });

    it('falls back to toLocaleString for an invalid zone (catch branch)', () => {
      expect(getCurrentTimeInTimezone('Invalid/Zone', 'fr-FR')).toBeTruthy();
    });
  });

  describe('getGreetingPeriod', () => {
    it.each([
      ['2025-01-15T06:00:00.000Z', 'morning'],
      ['2025-01-15T08:00:00.000Z', 'morning'],
      ['2025-01-15T12:00:00.000Z', 'lunch'],
      ['2025-01-15T14:00:00.000Z', 'afternoon'],
      ['2025-01-15T18:00:00.000Z', 'evening'],
      ['2025-01-15T22:00:00.000Z', 'night'],
      ['2025-01-15T23:00:00.000Z', 'night'],
    ])('maps %s (UTC) to %s', (iso, period) => {
      vi.setSystemTime(new Date(iso));
      expect(getGreetingPeriod('UTC')).toBe(period);
    });

    it('uses local time when no timezone is provided', () => {
      expect(['morning', 'lunch', 'afternoon', 'evening', 'night']).toContain(getGreetingPeriod());
    });

    it('falls back to afternoon for an invalid zone (catch branch)', () => {
      expect(getGreetingPeriod('Invalid/Zone')).toBe('afternoon');
    });
  });
});

describe('formatTimezoneDisplay', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-01-15T12:00:00.000Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('renders "City (UTC±N)" with underscores as spaces', () => {
    expect(formatTimezoneDisplay('Europe/Paris')).toBe('Paris (UTC+1)');
    expect(formatTimezoneDisplay('America/New_York')).toBe('New York (UTC-5)');
  });

  it('returns Unknown for an empty zone', () => {
    expect(formatTimezoneDisplay('')).toBe('Unknown');
  });
});

describe('groupTimezonesByRegion', () => {
  it('buckets zones by their region prefix', () => {
    expect(groupTimezonesByRegion(['Europe/Paris', 'Europe/London', 'America/New_York'])).toEqual({
      Europe: ['Europe/Paris', 'Europe/London'],
      America: ['America/New_York'],
    });
  });

  it('returns an empty object for no zones', () => {
    expect(groupTimezonesByRegion([])).toEqual({});
  });
});
