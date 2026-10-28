import { expect, it } from 'vitest';
import { seasonAt } from '../season';

it('uses the account civil month and offsets the southern calendar by six months', () => {
  const north = [
    'winter',
    'winter',
    'spring',
    'spring',
    'spring',
    'summer',
    'summer',
    'summer',
    'autumn',
    'autumn',
    'autumn',
    'winter',
  ];
  for (let month = 0; month < 12; month++) {
    const instant = Date.UTC(2026, month, 15);
    expect(seasonAt(instant, 'UTC', 'calendar', 'north')).toBe(north[month]);
    expect(seasonAt(instant, 'UTC', 'calendar', 'south')).toBe(north[(month + 6) % 12]);
  }
  const boundary = Date.parse('2026-03-01T00:30:00Z');
  expect(seasonAt(boundary, 'America/New_York', 'calendar', 'north')).toBe('winter');
  expect(seasonAt(boundary, 'Europe/Paris', 'calendar', 'north')).toBe('spring');
});
it('keeps missing/expired clock anchors neutral and permits explicit manual choices without a clock', () => {
  for (const time of [null, NaN, Infinity, 1e20])
    expect(seasonAt(time, 'UTC', 'calendar', 'north')).toBe('neutral');
  for (const zone of [null, '', 'Invalid/Zone'])
    expect(seasonAt(Date.now(), zone, 'calendar', 'north')).toBe('neutral');
  expect(seasonAt(null, null, 'off', 'south')).toBe('neutral');
  for (const manual of ['spring', 'summer', 'autumn', 'winter'] as const)
    expect(seasonAt(null, null, manual, 'south')).toBe(manual);
});
