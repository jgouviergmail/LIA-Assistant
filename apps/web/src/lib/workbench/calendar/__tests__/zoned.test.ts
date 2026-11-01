/**
 * Wall time ↔ instant for a zone, with Intl alone (ADR-369, Task 5.2, spec §14).
 *
 * The page writes what a clock on the account's wall would read, and reads an
 * instant back the same way. The two nights the clocks move are the cases that
 * matter: a minute that does not exist (spring forward) becomes the next one
 * that does, a minute that exists twice (fall back) is the earlier one.
 */

import { describe, expect, it } from 'vitest';

import { addDays, dayOfWeek, instantToWall, wallTimeToInstant, weekStart } from '../zoned';

const PARIS = 'Europe/Paris';

describe('instantToWall', () => {
  it('reads an instant on the zone’s wall', () => {
    expect(instantToWall(new Date('2026-11-02T09:00:00Z'), PARIS)).toEqual({
      date: '2026-11-02',
      time: '10:00',
    });
    expect(instantToWall(new Date('2026-11-02T23:30:00Z'), PARIS)).toEqual({
      date: '2026-11-03',
      time: '00:30',
    });
    expect(instantToWall(new Date('2026-11-02T09:00:00Z'), 'Asia/Kolkata')).toEqual({
      date: '2026-11-02',
      time: '14:30',
    });
  });
});

describe('wallTimeToInstant', () => {
  it('reads a wall time in its zone', () => {
    expect(wallTimeToInstant('2026-11-02', '10:00', PARIS).toISOString()).toBe(
      '2026-11-02T09:00:00.000Z'
    );
    expect(wallTimeToInstant('2026-07-01', '10:00', PARIS).toISOString()).toBe(
      '2026-07-01T08:00:00.000Z'
    );
    expect(wallTimeToInstant('2026-11-02', '14:30', 'Asia/Kolkata').toISOString()).toBe(
      '2026-11-02T09:00:00.000Z'
    );
  });

  it('moves a minute the spring-forward night skips to the next one that exists', () => {
    // 2026-03-29: Paris jumps from 02:00 to 03:00.
    expect(wallTimeToInstant('2026-03-29', '02:30', PARIS).toISOString()).toBe(
      '2026-03-29T01:00:00.000Z'
    );
    expect(instantToWall(wallTimeToInstant('2026-03-29', '02:30', PARIS), PARIS).time).toBe(
      '03:00'
    );
  });

  it('takes the earlier of a minute the fall-back night has twice', () => {
    // 2026-10-25: Paris goes from 03:00 back to 02:00; 02:30 happens at 00:30Z and 01:30Z.
    expect(wallTimeToInstant('2026-10-25', '02:30', PARIS).toISOString()).toBe(
      '2026-10-25T00:30:00.000Z'
    );
  });

  it('round-trips every minute of an ordinary day', () => {
    for (let minute = 0; minute < 24 * 60; minute += 17) {
      const time = `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
      expect(instantToWall(wallTimeToInstant('2026-11-02', time, PARIS), PARIS)).toEqual({
        date: '2026-11-02',
        time,
      });
    }
  });
});

describe('days', () => {
  it('counts days on the calendar, whatever the clocks do', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-28', 2)).toBe('2026-03-30');
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31');
  });

  it('starts a week on the first weekday asked', () => {
    expect(dayOfWeek('2026-11-01')).toBe(7);
    expect(weekStart('2026-11-01', 1)).toBe('2026-10-26');
    expect(weekStart('2026-10-26', 1)).toBe('2026-10-26');
    expect(weekStart('2026-11-04', 7)).toBe('2026-11-01');
  });
});
