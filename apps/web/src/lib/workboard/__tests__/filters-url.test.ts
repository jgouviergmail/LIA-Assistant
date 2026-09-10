/**
 * The board's filters in and out of the URL (ADR-276): a narrowed board is a
 * link, unknown values are dropped, the defaults leave no trace, and what is
 * not the filters' (the open ticket) survives a write.
 */
import { describe, it, expect } from 'vitest';

import {
  DEFAULT_FILTERS,
  SEARCH_MAX_CHARS,
  boardHref,
  filtersFromParams,
  writeFilters,
} from '@/lib/workboard/filters-url';

describe('filtersFromParams', () => {
  it('reads a plain URL as the default board', () => {
    expect(filtersFromParams(new URLSearchParams(''))).toEqual(DEFAULT_FILTERS);
  });

  it('reads every filter the board offers', () => {
    const params = new URLSearchParams(
      'status=todo&status=waiting&priority=urgent&assignee=lia&sort=due&overdue=1&q=salle'
    );

    expect(filtersFromParams(params)).toEqual({
      assignee: 'lia',
      sort: 'due',
      status: ['todo', 'waiting'],
      priority: ['urgent'],
      overdue: true,
      q: 'salle',
    });
  });

  it('drops what it does not know rather than trusting it', () => {
    const params = new URLSearchParams(
      'status=nope&status=done&priority=loud&assignee=bob&sort=random&overdue=yes&q=%20'
    );

    expect(filtersFromParams(params)).toEqual({
      assignee: 'all',
      sort: 'position',
      status: ['done'],
    });
  });
});

describe('writeFilters', () => {
  it('writes nothing for the default board', () => {
    expect(writeFilters(new URLSearchParams(''), DEFAULT_FILTERS).toString()).toBe('');
  });

  it('keeps the open ticket while it rewrites the filters', () => {
    const params = new URLSearchParams('ticket=t1&status=idea&q=old');

    const next = writeFilters(params, { assignee: 'me', sort: 'priority', overdue: true });

    expect(next.get('ticket')).toBe('t1');
    expect(next.getAll('status')).toEqual([]);
    expect(next.get('q')).toBeNull();
    expect(next.get('assignee')).toBe('me');
    expect(next.get('sort')).toBe('priority');
    expect(next.get('overdue')).toBe('1');
  });

  it('round-trips through the reader', () => {
    const filters = {
      assignee: 'peer' as const,
      sort: 'updated' as const,
      status: ['todo', 'in_progress'],
      priority: ['high', 'urgent'],
      overdue: true,
      q: 'devis',
    };

    expect(filtersFromParams(writeFilters(new URLSearchParams(''), filters))).toEqual(filters);
  });
});

describe('boardHref', () => {
  it('links to a plain board without a query string', () => {
    expect(boardHref('fr')).toBe('/fr/dashboard/workboard');
  });

  it('links into a narrowed board', () => {
    expect(boardHref('fr', { assignee: 'lia', overdue: true })).toBe(
      '/fr/dashboard/workboard?assignee=lia&overdue=1'
    );
  });
});

describe('the search term obeys the bound the API declares', () => {
  it('trims a URL carrying more than the API accepts', () => {
    const long = 'a'.repeat(SEARCH_MAX_CHARS + 50);
    const filters = filtersFromParams(new URLSearchParams(`q=${long}`));

    // Trimmed, not sent to be refused: `q` is capped at 200 server-side, and
    // a board answering « something went wrong » to a long paste says nothing
    // the person can act on.
    expect(filters.q).toHaveLength(SEARCH_MAX_CHARS);
  });

  it('leaves an ordinary term exactly as it was typed', () => {
    expect(filtersFromParams(new URLSearchParams('q=salle')).q).toBe('salle');
  });
});
