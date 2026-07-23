/**
 * useOpenLoops pure helpers (UXR Lot 7, B5) — direction grouping keeps the
 * server order, and the days-open badge maths.
 */

import { describe, it, expect } from 'vitest';

import { daysOpen, groupLoops, type OpenLoop } from '../useOpenLoops';

function loop(over: Partial<OpenLoop> = {}): OpenLoop {
  return {
    id: 'l-1',
    subject: 'rappeler le plombier',
    counterparty: null,
    direction: 'user_owes',
    due_hint: null,
    created_at: '2026-07-20T08:00:00Z',
    ...over,
  };
}

describe('groupLoops', () => {
  it('splits by direction preserving the server order', () => {
    const loops = [
      loop({ id: 'a', direction: 'user_owes' }),
      loop({ id: 'b', direction: 'waiting_on_other' }),
      loop({ id: 'c', direction: 'user_owes' }),
    ];
    const groups = groupLoops(loops);
    expect(groups.owed.map(l => l.id)).toEqual(['a', 'c']);
    expect(groups.waiting.map(l => l.id)).toEqual(['b']);
  });

  it('handles an empty ledger', () => {
    expect(groupLoops([])).toEqual({ owed: [], waiting: [] });
  });
});

describe('daysOpen', () => {
  it('floors to whole days and never goes negative', () => {
    const now = new Date('2026-07-23T09:00:00Z');
    expect(daysOpen('2026-07-20T08:00:00Z', now)).toBe(3);
    expect(daysOpen('2026-07-23T08:59:00Z', now)).toBe(0);
    expect(daysOpen('2026-07-24T00:00:00Z', now)).toBe(0); // clock skew
  });
});
