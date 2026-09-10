/**
 * What a gallery is narrowed to, counted and said (ADR-279).
 *
 * A folded filter block is an index entry: its badge and its line are what the
 * reader decides on before opening it. Both are pinned here, and so is the one
 * rule that is easy to get wrong — the SORT is not a narrowing.
 */

import { describe, expect, it } from 'vitest';

import {
  activeAssetFilterCount,
  describeAssetFilters,
  hasAssetFilters,
} from '@/lib/generated-assets/filters';
import type { GeneratedAssetFilters } from '@/types/generated-assets';

/** The caller's translator, echoing the key so an assertion names what it reads. */
const t = (key: string) => key;

describe('activeAssetFilterCount', () => {
  it('counts nothing on an untouched gallery', () => {
    expect(activeAssetFilterCount({})).toBe(0);
  });

  it('counts a search', () => {
    expect(activeAssetFilterCount({ q: 'bilan' })).toBe(1);
  });

  it('does not count a search made of spaces', () => {
    // The API trims it too: a badge lit by whitespace announces a narrowing
    // that never reached the server.
    expect(activeAssetFilterCount({ q: '   ' })).toBe(0);
  });

  it('counts the creation window ONCE whichever bound is set', () => {
    expect(activeAssetFilterCount({ createdAfter: '2026-09-01T00:00:00Z' })).toBe(1);
    expect(activeAssetFilterCount({ createdBefore: '2026-09-01T00:00:00Z' })).toBe(1);
    expect(
      activeAssetFilterCount({
        createdAfter: '2026-09-01T00:00:00Z',
        createdBefore: '2026-09-09T00:00:00Z',
      })
    ).toBe(1);
  });

  it('counts the expiry window on its own', () => {
    expect(activeAssetFilterCount({ expiresBefore: '2026-09-11T00:00:00Z' })).toBe(1);
  });

  it('NEVER counts the sort — it changes the order, not the set', () => {
    // Counting it would light the badge on an untouched gallery, and make an
    // empty result read as « no match » to somebody who merely reordered.
    expect(activeAssetFilterCount({ sort: 'name_asc' })).toBe(0);
    expect(hasAssetFilters({ sort: 'expires_asc' })).toBe(false);
  });

  it('adds up several narrowings', () => {
    const filters: GeneratedAssetFilters = {
      q: 'bilan',
      createdAfter: '2026-09-01T00:00:00Z',
      expiresBefore: '2026-09-11T00:00:00Z',
      sort: 'name_asc',
    };
    expect(activeAssetFilterCount(filters)).toBe(3);
    expect(hasAssetFilters(filters)).toBe(true);
  });
});

describe('describeAssetFilters', () => {
  it('says nothing about an untouched gallery', () => {
    expect(describeAssetFilters({}, t)).toBe('');
  });

  it('quotes the needle itself rather than naming the field', () => {
    // « Search » would say nothing about what the reader is looking at.
    expect(describeAssetFilters({ q: 'bilan' }, t)).toContain('bilan');
  });

  it('names each window in its control’s own words', () => {
    expect(describeAssetFilters({ createdAfter: '2026-09-01T00:00:00Z' }, t)).toBe(
      'settings.generated_assets.filters.created_active'
    );
    expect(describeAssetFilters({ expiresBefore: '2026-09-11T00:00:00Z' }, t)).toBe(
      'settings.generated_assets.filters.expiring_active'
    );
  });

  it('joins several narrowings with one separator, in control order', () => {
    const line = describeAssetFilters(
      { q: 'bilan', createdAfter: '2026-09-01T00:00:00Z', expiresBefore: '2026-09-11T00:00:00Z' },
      t
    );
    expect(line.split(' · ')).toHaveLength(3);
    expect(line.indexOf('bilan')).toBeLessThan(line.indexOf('created_active'));
    expect(line.indexOf('created_active')).toBeLessThan(line.indexOf('expiring_active'));
  });

  it('says nothing about a sort either', () => {
    expect(describeAssetFilters({ sort: 'name_asc' }, t)).toBe('');
  });

  it('describes exactly as many narrowings as it counts', () => {
    const filters: GeneratedAssetFilters = {
      q: 'bilan',
      createdBefore: '2026-09-09T00:00:00Z',
      expiresBefore: '2026-09-11T00:00:00Z',
    };
    // The badge and the line must agree: a « 3 » over a line naming two is the
    // reader discovering the third only after opening the block.
    expect(describeAssetFilters(filters, t).split(' · ')).toHaveLength(
      activeAssetFilterCount(filters)
    );
  });
});
