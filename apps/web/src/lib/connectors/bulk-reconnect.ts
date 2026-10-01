/**
 * Reconnecting several expired services with one provider authorization.
 *
 * Two surfaces offer it: « My connectors » in the settings, and the health
 * alert every dashboard page shows (a banner and a modal). Whether a row can
 * join the grouped consent is the SERVER's call — `bulk_reconnect_provider`,
 * the very rule the consent's plan applies — so neither surface guesses from a
 * connector type (the legacy `gmail` row, a row that is ACTIVE but unreadable).
 */

/** A provider with a grouped consent. */
export type BulkProvider = 'google' | 'microsoft';

/** What the grouped journey needs to know of one expired row. */
export interface BulkReconnectCandidate {
  id: string;
  connector_type: string;
  /** The account the row belongs to; two different ones cannot be grouped. */
  oauth_grant_id: string | null;
  /** That account's address, shown in the account-choice dialog. */
  oauth_account_email: string | null;
}

/** A row either surface lists: the settings' connector or a health item. */
export interface BulkReconnectSource {
  id: string;
  connector_type: string;
  bulk_reconnect_provider?: BulkProvider | null;
  oauth_grant_id?: string | null;
}

/** The providers in the order their buttons are offered. */
const PROVIDERS: readonly BulkProvider[] = ['google', 'microsoft'];

/**
 * The alert offers the grouped button only from two rows of one provider on:
 * a single broken service has its own « Reconnect » already.
 */
export const BULK_RECONNECT_ALERT_MIN = 2;

/**
 * The candidates of one provider among a surface's rows.
 *
 * @param rows - The rows the surface lists.
 * @param provider - The grouped consent asked for.
 * @param emailOf - Where the surface keeps the account address.
 * @returns The rows the server marked as joinable for that provider.
 */
export function bulkCandidates<Row extends BulkReconnectSource>(
  rows: readonly Row[],
  provider: BulkProvider,
  emailOf: (row: Row) => string | null | undefined
): BulkReconnectCandidate[] {
  return rows
    .filter(row => row.bulk_reconnect_provider === provider)
    .map(row => ({
      id: row.id,
      connector_type: row.connector_type,
      oauth_grant_id: row.oauth_grant_id ?? null,
      oauth_account_email: emailOf(row) ?? null,
    }));
}

/** One grouped button the alert offers. */
export interface BulkGroup {
  provider: BulkProvider;
  candidates: BulkReconnectCandidate[];
}

/**
 * The grouped buttons the health alert offers: one per provider holding at
 * least {@link BULK_RECONNECT_ALERT_MIN} joinable expired rows.
 *
 * @param rows - The broken connectors the alert shows.
 * @param emailOf - Where those rows keep the account address.
 * @returns The groups, Google first.
 */
export function alertBulkGroups<Row extends BulkReconnectSource>(
  rows: readonly Row[],
  emailOf: (row: Row) => string | null | undefined
): BulkGroup[] {
  return PROVIDERS.map(provider => ({
    provider,
    candidates: bulkCandidates(rows, provider, emailOf),
  })).filter(group => group.candidates.length >= BULK_RECONNECT_ALERT_MIN);
}
