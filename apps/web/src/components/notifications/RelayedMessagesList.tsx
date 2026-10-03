'use client';

/**
 * Relayed messages, as the hub lists them.
 *
 * Shows the CALLER's own side of each exchange — their directive when they
 * sent it, their assistant's rendering when they received it. Never the other
 * person's words: reading them here would undo the relay.
 *
 * The direction is carried by TRANSLATED TEXT, never by the arrow alone (the
 * icon is decorative), and a message the retention horizon has cleared says so
 * rather than rendering an empty line — the same rules the relationship sheet
 * already applies to the same data.
 */

import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  historyDateFormatter,
  NotificationHistoryItem,
  type NotificationHistoryRow,
} from '@/components/settings/NotificationHistoryList';
import { directionTone } from '@/lib/status-tone';

export interface RelayedMessage {
  id: string;
  peer_display_name: string;
  direction: string;
  content: string | null;
  occurred_at: string;
}

/**
 * Drawn as the hub's other histories draw their lines (`NotificationHistoryItem`,
 * owner 2026-10-03): the date, then the direction as the coloured marker, the
 * words, and the person as a chip.
 */
export function RelayedMessagesList({
  messages,
  locale,
}: {
  messages: readonly RelayedMessage[];
  locale: string;
}) {
  const { t } = useTranslation();
  const formatDate = historyDateFormatter(locale);

  return (
    <ul className="space-y-2" role="list">
      {messages.map(message => {
        const received = message.direction === 'received';
        const DirectionIcon = received ? ArrowDownLeft : ArrowUpRight;
        const row: NotificationHistoryRow = {
          id: message.id,
          createdAt: message.occurred_at,
          content: message.content,
          contentFallback: t('notifications_hub.message_no_content'),
          // A TONE per direction, not one colour for both: sent and received
          // were the same primary blue, so the only thing that separated them
          // was a 14 px arrow. The word stays — the tone is what makes the two
          // sides legible while scanning.
          badge: {
            label: received
              ? t('notifications_hub.direction_received')
              : t('notifications_hub.direction_sent'),
            tone: directionTone(message.direction),
            icon: <DirectionIcon className="h-3 w-3" aria-hidden="true" />,
          },
          chips: [{ key: 'peer', label: message.peer_display_name }],
        };
        return <NotificationHistoryItem key={message.id} row={row} formatDate={formatDate} />;
      })}
    </ul>
  );
}
