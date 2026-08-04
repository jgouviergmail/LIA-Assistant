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

import { formatInstant } from '@/lib/format-instant';

export interface RelayedMessage {
  id: string;
  peer_display_name: string;
  direction: string;
  content: string | null;
  occurred_at: string;
}

export function RelayedMessagesList({
  messages,
  locale,
}: {
  messages: readonly RelayedMessage[];
  locale: string;
}) {
  const { t } = useTranslation();

  return (
    <ul className="space-y-2" role="list">
      {messages.map(message => {
        const received = message.direction === 'received';
        const DirectionIcon = received ? ArrowDownLeft : ArrowUpRight;
        return (
          <li
            key={message.id}
            className="space-y-1 rounded-lg border border-border/40 bg-card/40 px-3 py-2"
          >
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
                <DirectionIcon className="h-3.5 w-3.5" aria-hidden="true" />
                {received
                  ? t('notifications_hub.direction_received')
                  : t('notifications_hub.direction_sent')}
              </span>
              <span className="text-sm font-medium text-foreground/90">
                {message.peer_display_name}
              </span>
              <time
                dateTime={message.occurred_at}
                className="text-[11px] tabular-nums text-muted-foreground"
              >
                {formatInstant(message.occurred_at, locale)}
              </time>
            </p>
            {message.content ? (
              // Plain React children: this echoes text a human wrote.
              <p className="whitespace-pre-line text-sm text-foreground/90">{message.content}</p>
            ) : (
              // Full `muted-foreground`, never a diluted /80: at this size the
              // faded pair measures under the 4.5:1 AA floor.
              <p className="text-xs italic text-muted-foreground">
                {t('notifications_hub.message_no_content')}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
