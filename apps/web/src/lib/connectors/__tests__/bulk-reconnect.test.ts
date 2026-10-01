/**
 * Which grouped « reconnect » buttons the health alert offers.
 *
 * The server says which rows the grouped consent accepts; the alert only
 * decides WHEN a group is worth a button: two joinable rows of one provider.
 */

import { describe, expect, it } from 'vitest';

import { alertBulkGroups, bulkCandidates, type BulkReconnectSource } from '../bulk-reconnect';

type Row = BulkReconnectSource & { email?: string | null };

function row(id: string, over: Partial<Row> = {}): Row {
  return {
    id,
    connector_type: 'google_calendar',
    bulk_reconnect_provider: 'google',
    oauth_grant_id: 'grant-a',
    email: 'someone@example.org',
    ...over,
  };
}

const emailOf = (r: Row) => r.email;

describe('bulkCandidates', () => {
  it('keeps the rows the server marked for that provider, with their account', () => {
    const rows = [
      row('a'),
      row('b', { bulk_reconnect_provider: null, connector_type: 'gmail' }),
      row('c', { bulk_reconnect_provider: 'microsoft' }),
      row('d', { oauth_grant_id: undefined, email: undefined }),
    ];

    expect(bulkCandidates(rows, 'google', emailOf)).toEqual([
      {
        id: 'a',
        connector_type: 'google_calendar',
        oauth_grant_id: 'grant-a',
        oauth_account_email: 'someone@example.org',
      },
      {
        id: 'd',
        connector_type: 'google_calendar',
        oauth_grant_id: null,
        oauth_account_email: null,
      },
    ]);
  });
});

describe('alertBulkGroups', () => {
  it('offers a provider from two joinable rows on', () => {
    const groups = alertBulkGroups([row('a'), row('b')], emailOf);

    expect(groups.map(group => group.provider)).toEqual(['google']);
    expect(groups[0].candidates.map(candidate => candidate.id)).toEqual(['a', 'b']);
  });

  it('offers nothing for one row per provider, however many are broken', () => {
    const rows = [row('a'), row('b', { bulk_reconnect_provider: 'microsoft' })];

    expect(alertBulkGroups(rows, emailOf)).toEqual([]);
  });

  it('does not count a row the grouped consent would refuse', () => {
    const rows = [
      row('a'),
      row('legacy', { connector_type: 'gmail', bulk_reconnect_provider: null }),
    ];

    expect(alertBulkGroups(rows, emailOf)).toEqual([]);
  });

  it('offers Google first, then Microsoft', () => {
    const rows = [
      row('m1', { bulk_reconnect_provider: 'microsoft' }),
      row('m2', { bulk_reconnect_provider: 'microsoft' }),
      row('g1'),
      row('g2'),
    ];

    expect(alertBulkGroups(rows, emailOf).map(group => group.provider)).toEqual([
      'google',
      'microsoft',
    ]);
  });
});
