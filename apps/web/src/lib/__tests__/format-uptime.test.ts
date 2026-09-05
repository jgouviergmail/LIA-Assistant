import { describe, expect, it } from 'vitest';

import { formatUptime } from '@/lib/format-uptime';

// Intl separates a number from its unit with a narrow no-break space in some
// locales; the assertion cares about the words, not the typography.
const plain = (text: string) => text.replace(/[  ]/g, ' ');

// A process uptime is read by a human deciding whether "a recent deployment"
// explains an incident (ADR-266). `M:SS` was ambiguous in a sentence; a
// locale unit is not, and it needs no translation key.
describe('formatUptime', () => {
  it('says minutes under an hour, in the reader locale', () => {
    expect(plain(formatUptime(2820, 'en'))).toBe('47 min');
    expect(plain(formatUptime(2820, 'fr'))).toBe('47 min');
  });

  it('says hours under a day', () => {
    expect(plain(formatUptime(2 * 3600 + 15 * 60, 'en'))).toMatch(/^2 hr/);
    expect(plain(formatUptime(2 * 3600 + 15 * 60, 'fr'))).toBe('2 h');
  });

  it('says days beyond a day', () => {
    expect(plain(formatUptime(3 * 86400 + 3600, 'en'))).toBe('3 days');
    expect(plain(formatUptime(3 * 86400 + 3600, 'de'))).toMatch(/^3 Tg/);
  });

  it('never goes negative and never throws on an unknown locale', () => {
    expect(plain(formatUptime(-5, 'en'))).toBe('0 min');
    expect(plain(formatUptime(90, 'xx-unknown'))).toBe('1 min');
  });
});
