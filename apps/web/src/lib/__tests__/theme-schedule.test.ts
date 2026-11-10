import { describe, expect, it } from 'vitest';
import * as schedule from '../theme-schedule';

describe('automatic light / absolute black', () => {
  it.each([
    ['2026-11-08T05:59:00Z', 'Europe/Paris', 420, 1200, 'dark'],
    ['2026-11-08T06:00:00Z', 'Europe/Paris', 420, 1200, 'light'],
    ['2026-11-08T19:00:00Z', 'Europe/Paris', 420, 1200, 'dark'],
    ['2026-11-08T23:00:00Z', 'UTC', 1200, 420, 'light'],
    ['2026-11-08T07:00:00Z', 'UTC', 1200, 420, 'dark'],
    ['2026-03-29T00:59:00Z', 'Europe/Paris', 150, 1200, 'dark'],
    ['2026-03-29T01:00:00Z', 'Europe/Paris', 150, 1200, 'light'],
    ['2026-10-25T00:30:00Z', 'Europe/Paris', 150, 1200, 'light'],
    ['2026-10-25T01:30:00Z', 'Europe/Paris', 150, 1200, 'light'],
    ['2026-11-08T01:15:00Z', 'Asia/Kathmandu', 420, 1200, 'light'],
  ] as const)('%s in %s follows civil time', (instant, timezone, light, dark, expected) => {
    expect(schedule.automaticThemeAt(Date.parse(instant), timezone, light, dark)).toEqual({
      mode: expected,
      oled: expected === 'dark',
    });
  });

  it('refuses an empty or all-day interval instead of choosing silently', () => {
    expect(() => schedule.automaticThemeAt(Date.now(), 'UTC', 420, 420)).toThrow();
  });
});
