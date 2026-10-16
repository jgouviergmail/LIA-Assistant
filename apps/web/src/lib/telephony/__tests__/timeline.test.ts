import { describe, expect, it } from 'vitest';
import { projectCallTimeline } from '../timeline';
import type { TelephonyCallSummary } from '@/types/telephony';

function call(
  id: string,
  created_at: string,
  overrides: Partial<TelephonyCallSummary> = {}
): TelephonyCallSummary {
  return {
    id,
    created_at,
    callee_display: id,
    objective: 'Discuss the appointment',
    status: 'completed',
    outcome: null,
    summary: null,
    debrief: null,
    call_seconds: null,
    completed_at: null,
    call_kind: 'third_party',
    call_mode: 'direct',
    relay_outcome: null,
    ...overrides,
  };
}

describe('call timeline — actual instants in the display zone', () => {
  it('groups contiguous local start dates while preserving the API page order', () => {
    const calls = [call('late', '2026-10-13T22:15:00Z'), call('earlier', '2026-10-13T18:00:00Z')];
    const { days } = projectCallTimeline(calls, 'fr', 'Europe/Paris');
    expect(days.map(day => day.key)).toEqual(['2026-10-14', '2026-10-13']);
    expect(days[0].label).toMatch(/mercredi 14 octobre 2026/);
    expect(days[0].dayNumber).toBe('14');
    expect(days[0].month).toBe(
      new Intl.DateTimeFormat('fr', { timeZone: 'Europe/Paris', month: 'short' }).format(
        new Date('2026-10-13T22:15:00Z')
      )
    );
    expect(days[0].entries[0].start).toBe('00:15');
    expect(days.flatMap(day => day.entries.map(entry => entry.call))).toEqual(calls);
    expect(projectCallTimeline(calls, 'fr', 'UTC').days).toHaveLength(1);
  });

  it('retains malformed dates and out-of-order revisits with distinct group identifiers', () => {
    const calls = [
      call('a', '2026-10-13T10:00:00Z'),
      call('bad', 'invalid'),
      call('b', '2026-10-13T11:00:00Z'),
      call('bad2', 'invalid'),
    ];
    const { days } = projectCallTimeline(calls, 'de', 'America/New_York');
    expect(days.map(day => day.key)).toEqual(['2026-10-13', 'unknown', '2026-10-13', 'unknown']);
    expect(new Set(days.map(day => day.id)).size).toBe(4);
    expect(days[1].label).toBeNull();
    expect(days[1].dayNumber).toBeNull();
    expect(days[1].month).toBeNull();
    expect(days[1].entries[0].start).toBeNull();
    expect(days.flatMap(day => day.entries.map(entry => entry.call.id))).toEqual([
      'a',
      'bad',
      'b',
      'bad2',
    ]);
    expect(projectCallTimeline([], 'fr', 'UTC').days).toEqual([]);
  });

  it('never infers a finish from duration and never displays an active or backwards finish', () => {
    const calls = [
      call('duration-only', '2026-10-13T10:00:00Z', { call_seconds: 100 }),
      call('bad-end', '2026-10-13T10:00:00Z', { completed_at: 'invalid' }),
      call('backwards', '2026-10-13T10:00:00Z', { completed_at: '2026-10-13T09:59:00Z' }),
      call('active', '2026-10-13T10:00:00Z', {
        status: 'in_progress',
        completed_at: '2026-10-13T10:01:00Z',
      }),
      call('dialing', '2026-10-13T10:00:00Z', {
        status: 'dialing',
        completed_at: '2026-10-13T10:01:00Z',
      }),
    ];
    const { days } = projectCallTimeline(calls, 'en', 'UTC');
    expect(days[0].entries.map(entry => entry.end)).toEqual([null, null, null, null, null]);
    expect(days[0].entries.every(entry => entry.endDay === null)).toBe(true);
  });

  it('keeps a zero duration and a real simultaneous finish without discarding either', () => {
    const record = call('zero', '2026-10-13T10:00:00Z', {
      call_seconds: 0,
      completed_at: '2026-10-13T10:00:00Z',
    });
    const entry = projectCallTimeline([record], 'fr', 'UTC').days[0].entries[0];
    expect(entry.start).toBe('10:00');
    expect(entry.end).toBe('10:00');
    expect(entry.call.call_seconds).toBe(0);
    expect(entry.endDay).toBeNull();
  });

  it('includes the local end date across midnight independently of UTC dates', () => {
    const record = call('midnight', '2026-10-13T21:50:00Z', {
      completed_at: '2026-10-13T22:10:00Z',
    });
    const entry = projectCallTimeline([record], 'fr', 'Europe/Paris').days[0].entries[0];
    expect(entry.start).toBe('23:50');
    expect(entry.end).toBe('00:10');
    expect(entry.endDay).toMatch(/14 oct/);
  });

  it('disambiguates repeated local times on daylight-saving fallback', () => {
    const record = call('fall-back', '2026-10-25T00:30:00Z', {
      completed_at: '2026-10-25T01:30:00Z',
    });
    const entry = projectCallTimeline([record], 'fr', 'Europe/Paris').days[0].entries[0];
    expect(entry.start).toMatch(/02:30.*UTC\+2/);
    expect(entry.end).toMatch(/02:30.*UTC\+1/);
    expect(entry.endDay).toBeNull();
  });

  it('discloses the offset change on daylight-saving spring-forward', () => {
    const record = call('spring', '2026-03-29T00:30:00Z', { completed_at: '2026-03-29T01:30:00Z' });
    const entry = projectCallTimeline([record], 'fr', 'Europe/Paris').days[0].entries[0];
    expect(entry.start).toMatch(/01:30.*UTC\+1/);
    expect(entry.end).toMatch(/03:30.*UTC\+2/);
  });

  it('keeps a trustworthy completed instant with its date when the start is unknown', () => {
    const record = call('unknown-start', 'invalid', { completed_at: '2026-10-13T10:30:00Z' });
    const entry = projectCallTimeline([record], 'fr', 'UTC').days[0].entries[0];
    expect(entry.start).toBeNull();
    expect(entry.end).toBe('10:30');
    expect(entry.endDay).toMatch(/13 oct/);
  });
});
