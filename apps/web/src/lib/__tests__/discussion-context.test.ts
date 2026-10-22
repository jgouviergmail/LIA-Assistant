import { describe, expect, it } from 'vitest';
import { contextTimeline, contextUsability } from '../discussion-context';

describe('discussion context controls', () => {
  it('blocks descendants even when the excluded item is on another page', () => {
    const item = { proofs: [{ root: 'shared', support_roots: [], source: 'calendar' }] };
    expect(contextUsability(item, [{ item_id: 'old-item', roots: ['shared'] }], ['calendar'])).toBe(
      'excluded'
    );
  });
  it('distinguishes a withdrawn source from an explicit non-use choice', () => {
    const item = { proofs: [{ root: 'native', support_roots: ['known'], source: 'portrait' }] };
    expect(contextUsability(item, [], [])).toBe('source_disabled');
    expect(contextUsability(item, [{ item_id: 'prior', roots: ['known'] }], ['portrait'])).toBe(
      'excluded'
    );
    expect(contextUsability(item, [], ['portrait'])).toBe('usable');
  });
});

describe('the period and last reading of an item', () => {
  it('spans the evidence it rests on, in time order, whatever the proofs order', () => {
    const timeline = contextTimeline({
      proofs: [
        { occurred_at: '2026-10-12T09:00:00Z', observed_at: '2026-10-20T08:00:00Z' },
        { occurred_at: '2026-10-03T18:00:00Z', observed_at: '2026-10-21T07:30:00Z' },
      ],
    });
    expect(timeline).toEqual({
      start: '2026-10-03T18:00:00Z',
      end: '2026-10-12T09:00:00Z',
      updated: '2026-10-21T07:30:00Z',
    });
  });
  it('states no period when no proof says when it happened', () => {
    // A recording date is not an occurrence: the absence stays visible.
    expect(
      contextTimeline({ proofs: [{ occurred_at: null, observed_at: '2026-10-20T08:00:00Z' }] })
    ).toEqual({ start: null, end: null, updated: '2026-10-20T08:00:00Z' });
  });
});
