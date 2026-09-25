'use client';

/**
 * The sent-broadcasts history an administrator reads under the send form (ADR-312).
 *
 * One paginated list with the EXACT total behind it (ADR-185), served by
 * `GET /notifications/admin/broadcasts`. It rides `usePagedSection` — the paging
 * contract the notifications hub already shares — rather than a sixth copy of
 * it; `refreshKey` is bumped by the send form, so a broadcast just sent appears
 * at the top without the list ever being unmounted.
 */

import { usePagedSection, type PagedSection } from './usePagedSection';

/** Who a broadcast was addressed to — the backend's `BroadcastAudience`. */
export type BroadcastAudience = 'all' | 'selected';

/** One named recipient of a targeted broadcast. */
export interface BroadcastRecipient {
  id: string;
  full_name: string | null;
  email: string;
}

/** One sent broadcast, as `GET /notifications/admin/broadcasts` describes it. */
export interface BroadcastHistoryItem {
  id: string;
  /** The message as the admin wrote it — never a translation. */
  message: string;
  /** ISO-8601 send instant. */
  sent_at: string;
  sender_name: string | null;
  audience: BroadcastAudience;
  /** The first recipients of a selected broadcast, in name order. */
  recipients: BroadcastRecipient[];
  /** EXACT number of recipient accounts that still exist. */
  recipients_total: number;
  /** Accounts the send reached at send time (delivery, not the addressed selection). */
  reached_count: number;
  /** ISO-8601 expiry instant; null = never. */
  expires_at: string | null;
  /** The delay chosen at send time, in days; null = never. */
  expires_in_days: number | null;
  is_expired: boolean;
  fcm_sent: number;
  fcm_failed: number;
  /** Accounts that dismissed it (exact). */
  read_count: number;
}

/** A page of the history and the exact total behind it. */
export interface BroadcastHistoryPage {
  items: BroadcastHistoryItem[];
  total: number;
}

/** Rows per page — a history is read a few rows at a time. */
export const BROADCAST_HISTORY_PAGE_SIZE = 10;

export const BROADCAST_HISTORY_PATH = '/notifications/admin/broadcasts';

/**
 * The sent-broadcasts history, one page at a time.
 *
 * @param refreshKey - Bumped after a send: refetch from the first page.
 * @returns The paged section (items, exact total, paging, first-load flag).
 */
export function useBroadcastHistory(refreshKey: number): PagedSection<BroadcastHistoryItem> {
  return usePagedSection<BroadcastHistoryPage, BroadcastHistoryItem>({
    path: BROADCAST_HISTORY_PATH,
    selectItems: page => page.items,
    selectTotal: page => page.total,
    enabled: true,
    pageSize: BROADCAST_HISTORY_PAGE_SIZE,
    refreshKey,
  });
}
