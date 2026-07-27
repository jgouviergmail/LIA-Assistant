/**
 * Condensation rule for connector notices (S4).
 *
 * A single expired Google refresh token invalidates Gmail, Calendar and Drive
 * at once, so one failure can stack three amber rows in the band between the
 * thread and the composer — ~120 px on a surface S0 measured as already tight
 * (443 px of chrome on a 716 px shell before arbitration).
 *
 * The rule is deliberately conservative: notices condense ONLY when they all
 * carry the same action. "Reconnect Gmail" and "Calendar is rate-limited" have
 * different remedies, and any single-sentence summary of the two would be
 * false for one of them. Mixed sets therefore stay listed in full — rarer, and
 * honest.
 */

import type { ConnectorNotice } from '@/types/chat-state';

export interface NoticeSummary {
  /** The action every notice in the set shares. */
  action: ConnectorNotice['action'];
  /** How many notices it stands for. */
  count: number;
}

/**
 * Summarise a set of notices, when it can be done without losing meaning.
 *
 * Args:
 *   notices: The pending notices, in display order.
 *
 * Returns:
 *   A summary when there are at least two notices sharing one action;
 *   `null` when the set is empty, has a single entry (which already states
 *   exactly what happened), or mixes actions.
 */
export function summarizeNotices(notices: readonly ConnectorNotice[]): NoticeSummary | null {
  if (notices.length < 2) return null;

  const [first, ...rest] = notices;
  if (rest.some(notice => notice.action !== first.action)) return null;

  return { action: first.action, count: notices.length };
}
