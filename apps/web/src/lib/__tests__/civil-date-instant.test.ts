import { expect, it } from 'vitest';
import { civilDateInstant } from '../civil-date-instant';
it.each([
  ['2026-03-29', 'Europe/Paris', '2026-03-28T23:00:00.000Z'],
  ['2026-03-30', 'Europe/Paris', '2026-03-29T22:00:00.000Z'],
  ['2026-10-25', 'Europe/Paris', '2026-10-24T22:00:00.000Z'],
  ['2026-10-26', 'Europe/Paris', '2026-10-25T23:00:00.000Z'],
  ['2026-01-01', 'Asia/Kathmandu', '2025-12-31T18:15:00.000Z'],
  ['2026-11-01', 'America/Havana', '2026-11-01T04:00:00.000Z'],
])('converts %s in %s independently of the device timezone', (day, zone, expected) => {
  expect(civilDateInstant(day, zone)).toBe(expected);
});
it.each([
  ['2026-02-30', 'Europe/Paris'],
  ['2011-12-30', 'Pacific/Apia'],
  ['2026-01-01', 'Invalid/Zone'],
])('refuses nonexistent date or zone %s %s', (day, zone) => {
  expect(() => civilDateInstant(day, zone)).toThrow();
});
