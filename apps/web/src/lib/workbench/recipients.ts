/**
 * The workbench's door to contact suggestions for an address being typed (ADR-369).
 *
 * A message's recipients and an event's guests read the same matcher as « Send by
 * e-mail » — the account's contacts, by name, first name or number (owner, 2026-10-31).
 * Each field reads the shortest query searched from its own tool's bounds
 * (`recipient_query_min_chars`).
 */
export const WORKBENCH_RECIPIENTS_PATH = '/workbench/mail/recipients';
