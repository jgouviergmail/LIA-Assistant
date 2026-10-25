import { describe, expect, it } from 'vitest';

import type { RelationContext } from '@/hooks/useRelations';
import {
  entryOf,
  groupByDay,
  mergeEntries,
  providerEntries,
  type TimelineEntry,
} from '../timeline';

const entry = (key: string, at: string): TimelineEntry => ({
  key,
  kind: 'memory',
  at,
  text: key,
  detail: null,
});

describe('relationship timeline', () => {
  it('words each record as its section does', () => {
    expect(
      entryOf({
        kind: 'call',
        at: '2026-10-20T09:00:00Z',
        call: {
          id: 'c1',
          objective: 'Ask about Sunday',
          outcome: null,
          summary: 'She is free.',
          created_at: '2026-10-20T09:00:00Z',
        },
      })
    ).toEqual({
      key: 'call:c1',
      kind: 'call',
      at: '2026-10-20T09:00:00Z',
      text: 'Ask about Sunday',
      detail: 'She is free.',
    });
  });

  it('weaves in only the provider items the base pages already cover', () => {
    const base = [entry('b1', '2026-10-20T10:00:00Z'), entry('b2', '2026-10-10T10:00:00Z')];
    const provider = [
      entry('inside', '2026-10-15T10:00:00Z'),
      entry('older', '2026-09-01T10:00:00Z'),
    ];

    expect(mergeEntries(base, provider, false).map(e => e.key)).toEqual(['b1', 'inside', 'b2']);
    // Once the base is exhausted every provider item belongs.
    expect(mergeEntries(base, provider, true).map(e => e.key)).toEqual([
      'b1',
      'inside',
      'b2',
      'older',
    ]);
  });

  it('keeps the meetings still to come apart, soonest first', () => {
    const section = (events: RelationContext['events']['events']): RelationContext['events'] => ({
      status: 'ok',
      from_cache: false,
      generated_at: '2026-10-24T00:00:00Z',
      contact: null,
      emails: [],
      events,
    });
    const event = (id: string, starts_at: string, is_past: boolean) => ({
      id,
      summary: id,
      starts_at,
      ends_at: null,
      is_past,
      role: 'attendee' as const,
      organizer_known: true,
    });
    const context: RelationContext = {
      contact: section([]),
      emails: section([]),
      events: section([
        event('later', '2026-11-20T10:00:00Z', false),
        event('soon', '2026-10-30T10:00:00Z', false),
        event('done', '2026-10-01T10:00:00Z', true),
      ]),
      addresses_used: 1,
      window_days: 30,
      email_window_days: 90,
    };

    const { past, upcoming } = providerEntries(context);
    expect(upcoming.map(e => e.key)).toEqual(['event:soon', 'event:later']);
    expect(past.map(e => e.key)).toEqual(['event:done']);
  });

  it('groups contiguous civil days of the reader’s zone', () => {
    // 23:30 and 22:30 UTC are both past midnight in Paris (the 21st); 21:30
    // UTC is still the 20th there — the reader's day, not the server's.
    const days = groupByDay(
      [
        entry('late', '2026-10-20T23:30:00Z'),
        entry('after-midnight-in-paris', '2026-10-20T22:30:00Z'),
        entry('evening', '2026-10-20T21:30:00Z'),
        entry('previous', '2026-10-19T08:00:00Z'),
      ],
      'en',
      'Europe/Paris'
    );
    expect(days.map(day => day.entries.map(e => e.key))).toEqual([
      ['late', 'after-midnight-in-paris'],
      ['evening'],
      ['previous'],
    ]);
  });
});
