'use client';

/**
 * Relayed messages, as the hub lists them.
 *
 * Shows the CALLER's own side of each exchange — their directive when they
 * sent it, their assistant's rendering when they received it. Never the other
 * person's words: reading them here would undo the relay.
 *
 * The direction and attribution are translated text, and a message the retention horizon has cleared says so
 * rather than rendering an empty line — the same rules the relationship sheet
 * already applies to the same data.
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import {
  historyDateFormatter,
  NotificationHistoryItem,
  type NotificationHistoryRow,
  type NotificationHistoryPresentation,
} from '@/components/settings/NotificationHistoryList';
import { directionTone } from '@/lib/status-tone';

/** A private-use character: no translation or display name carries one. */
const NAME_SLOT = '';

/**
 * « de **Camille** » — the sentence stays the translator's, the name alone in
 * bold (owner request 2026-10-21). The name is placed as a React CHILD, never
 * interpolated into markup: a peer chooses their own display name, and a
 * `<Trans>` string would parse whatever tags it carried.
 */
function attributionOf(sentence: string, name: string): ReactNode {
  if (!sentence.includes(NAME_SLOT)) return sentence;
  const [before, after = ''] = sentence.split(NAME_SLOT);
  return (
    <>
      {before}
      <strong className="font-semibold">{name}</strong>
      {after}
    </>
  );
}

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
 * person beside its direction, then the message.
 */
export function RelayedMessagesList({
  messages,
  locale,
  presentation = 'panels',
}: {
  presentation?: NotificationHistoryPresentation;
  messages: readonly RelayedMessage[];
  locale: string;
}) {
  const { t } = useTranslation();
  const formatDate = historyDateFormatter(locale);

  return (
    <ul className={presentation === 'timeline' ? 'min-w-0' : 'space-y-2'} role="list">
      {messages.map(message => {
        const received = message.direction === 'received';
        const row: NotificationHistoryRow = {
          id: message.id,
          createdAt: message.occurred_at,
          content: message.content,
          contentFallback: t('notifications_hub.message_no_content'),
          // A TONE per direction, not one colour for both: sent and received
          // were the same primary blue, so the only thing that separated them
          // was an arrow. The word stays — the tone is what makes the two
          // sides legible while scanning.
          badge: {
            label: received
              ? t('notifications_hub.direction_received')
              : t('notifications_hub.direction_sent'),
            tone: directionTone(message.direction),
          },
          attribution: attributionOf(
            t(received ? 'notifications_hub.from_peer' : 'notifications_hub.to_peer', {
              name: NAME_SLOT,
            }),
            message.peer_display_name
          ),
          chips: [],
        };
        return (
          <NotificationHistoryItem
            key={message.id}
            row={row}
            formatDate={formatDate}
            presentation={presentation}
          />
        );
      })}
    </ul>
  );
}
