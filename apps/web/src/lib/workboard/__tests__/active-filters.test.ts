/**
 * What the board is narrowed to, said in one line (ADR-276).
 *
 * The filter block folds on a phone, so what it holds has to be readable
 * BEFORE opening it — otherwise the reader opens it to find out, which is
 * exactly the scanning a fold exists to spare them (the `Disclosure`
 * doctrine). Two answers: how MANY narrowings are active (an exact count,
 * ADR-185) and WHICH ones, as the very words the controls carry.
 */

import { describe, expect, it } from 'vitest';

import { activeFilterCount, describeFilters, hasFilters } from '@/lib/workboard/active-filters';
import { DEFAULT_FILTERS } from '@/lib/workboard/filters-url';
import type { BoardFilters } from '@/types/workboard';

/** The controls' own labels, resolved the way the component resolves them. */
const t = (key: string) => key;

describe('hasFilters', () => {
  it('reads an untouched board as not narrowed', () => {
    expect(hasFilters(DEFAULT_FILTERS)).toBe(false);
    expect(hasFilters({})).toBe(false);
  });

  it('does not count the sort as a narrowing', () => {
    // Sorting changes the ORDER, never the set: « no match » must not be
    // announced because somebody sorted by due date.
    expect(hasFilters({ ...DEFAULT_FILTERS, sort: 'due' })).toBe(false);
  });

  it('does not count « anyone » as a narrowing', () => {
    expect(hasFilters({ assignee: 'all' })).toBe(false);
  });

  it('does not count a blank search as a narrowing', () => {
    expect(hasFilters({ q: '   ' })).toBe(false);
  });

  it.each([
    ['a search', { q: 'salle' }],
    ['overdue only', { overdue: true }],
    ['a priority', { priority: ['high'] }],
    ['a column', { status: ['todo'] }],
    ['a holder', { assignee: 'lia' as const }],
  ])('counts %s as a narrowing', (_label, filters) => {
    expect(hasFilters(filters as BoardFilters)).toBe(true);
  });
});

describe('activeFilterCount', () => {
  it('is zero on an untouched board', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
  });

  it('counts each narrowing once, whatever its cardinality', () => {
    // Two priorities are ONE narrowing: the badge answers "how many controls
    // are set", not "how many values were picked".
    expect(activeFilterCount({ priority: ['high', 'urgent'] })).toBe(1);
  });

  it('adds up every family', () => {
    expect(
      activeFilterCount({
        q: 'salle',
        overdue: true,
        priority: ['high'],
        status: ['todo'],
        assignee: 'me',
      })
    ).toBe(5);
  });

  it('ignores the sort and the paging', () => {
    expect(activeFilterCount({ sort: 'due', limit: 50, offset: 20 })).toBe(0);
  });
});

describe('describeFilters', () => {
  it('says nothing when nothing narrows the board', () => {
    expect(describeFilters(DEFAULT_FILTERS, t)).toBe('');
  });

  it('names the holder with the control’s own word', () => {
    expect(describeFilters({ assignee: 'lia' }, t)).toBe('workboard.filters.side_lia');
  });

  it('names the priority with the control’s own word', () => {
    expect(describeFilters({ priority: ['urgent'] }, t)).toBe('workboard.priority.urgent');
  });

  it('quotes the search term itself rather than naming the field', () => {
    // « Search » says nothing; the needle is the information.
    expect(describeFilters({ q: 'salle' }, t)).toContain('salle');
  });

  it('joins several narrowings with a middle dot', () => {
    const described = describeFilters({ assignee: 'me', overdue: true }, t);
    expect(described).toBe('workboard.filters.side_me · workboard.filters.overdue');
  });

  it('lists every picked priority', () => {
    expect(describeFilters({ priority: ['high', 'urgent'] }, t)).toBe(
      'workboard.priority.high, workboard.priority.urgent'
    );
  });

  it('trims the search needle it quotes', () => {
    expect(describeFilters({ q: '  salle  ' }, t)).toContain('salle');
    expect(describeFilters({ q: '  salle  ' }, t)).not.toContain('  salle');
  });

  it('keeps the order the controls are read in', () => {
    const described = describeFilters(
      { q: 'x', assignee: 'peer', priority: ['low'], status: ['done'], overdue: true },
      t
    );
    const parts = described.split(' · ');
    expect(parts[0]).toContain('x');
    expect(parts[1]).toBe('workboard.filters.side_peer');
    expect(parts[2]).toBe('workboard.priority.low');
    expect(parts[3]).toBe('workboard.columns.done');
    expect(parts[4]).toBe('workboard.filters.overdue');
  });
});
