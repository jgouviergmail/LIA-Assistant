'use client';

import { useApiQuery } from './useApiQuery';
import type { ConnectionView } from './usePeerConnections';

/**
 * The people this account may relay a message to.
 *
 * Deliberately NOT `usePeerConnections`: that hook is the settings panel's,
 * and it issues FIVE queries (`/peers/me`, `/requests`, `/connections`,
 * `/blocks`, `/access-log`) because the panel shows all of it. The share menu
 * lives on every assistant bubble, so using it there cost 5 requests per
 * message — measured at 120 calls on a twelve-answer conversation, 80 % of
 * them for data the menu never reads.
 *
 * One endpoint, and only while the caller asks for it.
 *
 * @param enabled - Fetch only when the menu is open; a closed menu on twenty
 *   bubbles must cost nothing. `useApiQuery` keeps what it already has when
 *   this goes back to false, so re-opening is instant.
 * @returns Accepted connections only — a pending request is not a channel,
 *   and offering it would promise a delivery the backend refuses.
 */
export function usePeerRecipients(enabled: boolean): ConnectionView[] {
  const { data } = useApiQuery<ConnectionView[]>('/peers/connections', {
    componentName: 'usePeerRecipients',
    enabled,
  });
  return (data ?? []).filter(connection => connection.status === 'accepted');
}
