import { expect, it, vi } from 'vitest';
import { readWorldEnvironment, atmosphereAt } from '../atmosphere';

it('uses the server anchor and native timezone even when the device civil clock is wrong', () => {
  const now = Date.parse('2026-10-23T00:00:00Z');
  const context = readWorldEnvironment(
    { server_time: now / 1000, timezone: 'Europe/Paris', weather: null },
    50
  );
  const wrongClock = vi.spyOn(Date, 'now').mockReturnValue(0);
  expect(atmosphereAt(context, 1050).phase).toBe('night');
  expect(atmosphereAt(context, 1050).weather).toBe('neutral');
  wrongClock.mockRestore();
});

it('drops stale or future weather and rejects malformed context without inventing a climate', () => {
  const now = Date.parse('2026-10-23T12:00:00Z');
  const context = readWorldEnvironment(
    {
      server_time: now / 1000,
      timezone: 'UTC',
      weather: {
        temperature_c: 12,
        condition_code: 'Rain',
        wind_speed_kmh: 4,
        observed_at: new Date(now - 60_000).toISOString(),
        expires_at: new Date(now + 1000).toISOString(),
      },
    },
    0
  );
  expect(atmosphereAt(context, 500).weather).toBe('rain');
  expect(atmosphereAt(context, 1001).weather).toBe('neutral');
  expect(readWorldEnvironment({ server_time: Number.NaN, timezone: 'PRIVATE_BAD' }, 0)).toBeNull();
  expect(atmosphereAt(null, 0).phase).toBe('unknown');
});
