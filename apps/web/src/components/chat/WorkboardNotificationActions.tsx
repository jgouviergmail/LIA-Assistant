'use client';
/**
 * What a ticket notification lets you do, right under the bubble (ADR-276).
 *
 * The `PeerMessageActions` precedent: a self-gated, metadata-driven block that
 * renders NOTHING unless the bubble is a `proactive_workboard` notification.
 *
 * The three links come from the metadata the backend put there — never rebuilt
 * here. `board_url` and `ticket_url` are absolute URLs the API composed from
 * its own `FRONTEND_URL`, and the `intent` is the sentence LIA is asked to
 * finish the run with: composing either of them a second time in the frontend
 * would be a second authority on where a ticket lives.
 *
 * « Finish in the chat » appears for the `waiting` event ALONE — the one case
 * where a run stopped because it needed the person. Offering it on a finished
 * run would invite a turn with nothing to do.
 */
import Link from 'next/link';
import { ExternalLink, LayoutGrid, MessageSquarePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/** The fields a workboard notification carries (see `notification_metadata`). */
interface WorkboardMetadata {
  ticketUrl: string | null;
  boardUrl: string | null;
  intentUrl: string | null;
}

/** Read one string field, or null when absent or mistyped. */
function str(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/**
 * Whether this bubble is a workboard notification, and what it points at.
 *
 * @param metadata - The message metadata, possibly absent.
 * @returns The links, or null when the bubble is something else entirely.
 */
export function workboardNotification(
  metadata: Record<string, unknown> | undefined
): WorkboardMetadata | null {
  if (!metadata || metadata.type !== 'proactive_workboard') return null;
  return {
    ticketUrl: str(metadata, 'ticket_url'),
    boardUrl: str(metadata, 'board_url'),
    // `intent`, the key `notification_metadata` writes — present on the
    // `waiting` event ALONE, where the run stopped needing the person. Pinned
    // by `test_notification_metadata_contract.py`: a rename backend-side that
    // this file did not follow would silently drop the one action that
    // finishes a stopped run.
    intentUrl: str(metadata, 'intent'),
  };
}

export interface WorkboardNotificationActionsProps {
  metadata: Record<string, unknown> | undefined;
}

export function WorkboardNotificationActions({ metadata }: WorkboardNotificationActionsProps) {
  const { t } = useTranslation();
  const links = workboardNotification(metadata);
  if (!links) return null;

  const chip =
    'inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-2 py-1 text-xs hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-2"
      role="group"
      aria-label={t('workboard.notification.actions_label')}
    >
      {links.ticketUrl && (
        <Link href={links.ticketUrl} className={chip}>
          <LayoutGrid className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          {t('workboard.actions.open_ticket')}
        </Link>
      )}
      {links.boardUrl && (
        <Link href={links.boardUrl} className={chip}>
          <ExternalLink className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          {t('workboard.actions.open_board')}
        </Link>
      )}
      {links.intentUrl && (
        <Link href={links.intentUrl} className={chip}>
          <MessageSquarePlus className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          {t('workboard.actions.finish_in_chat')}
        </Link>
      )}
    </div>
  );
}
