'use client';

/**
 * ConversationBand — what was said around the open message (ADR-369, lot 8.1).
 *
 * It sits under the reader's toolbar, outside the message, so it neither moves the words
 * nor leaves while the next message loads, and the focus stays on the link it was on: every
 * row is a link, the open message's included. A message alone says nothing, and neither
 * does a conversation still on its way; one that could not be read says so (ADR-292). The
 * number is exact, or the rows are stated as the latest ones (ADR-185).
 */
import { ChevronDown, MessagesSquare } from 'lucide-react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { addressLabel } from '@/lib/workbench/mail';
import type { MailSummary } from '@/lib/workbench/types';

import { isPlainClick } from './MessageRow';
import type { ConversationState } from './useMailScreen';

export interface ConversationBandProps {
  lng: Language;
  conversation: ConversationState;
  /** The message on screen. */
  openId: string | null;
  /** How the list tells when a message arrived, or null. */
  whenOf: (message: { received_at: string | null }) => string | null;
  hrefOf: (message: MailSummary) => string;
  /** Opens a message in the place of the open one. */
  onOpen: (message: MailSummary) => void;
}

export function ConversationBand({
  lng,
  conversation,
  openId,
  whenOf,
  hrefOf,
  onOpen,
}: ConversationBandProps) {
  const { t } = useTranslation(lng);
  const { rows, truncated, failed, expanded, setExpanded } = conversation;
  if (failed) {
    return (
      <p role="status" className="border-b px-4 py-1.5 text-xs text-muted-foreground">
        {t('workbench.mail.conversation_failed')}
      </p>
    );
  }
  if (rows.length < 2) return null;
  const said = truncated
    ? 'workbench.mail.conversation_latest'
    : 'workbench.mail.conversation_count';
  return (
    <div className="border-b">
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
        className="h-9 w-full justify-start gap-2 rounded-none px-4 text-muted-foreground"
      >
        <MessagesSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate">{t(said, { count: rows.length })}</span>
        <ChevronDown
          className={cn('ml-auto h-4 w-4 shrink-0 transition-transform', expanded && 'rotate-180')}
          aria-hidden="true"
        />
      </Button>
      {expanded && (
        <ol
          aria-label={t('workbench.mail.conversation_title')}
          className="max-h-56 overflow-y-auto border-t"
        >
          {rows.map(row => (
            <li key={row.id}>
              <Link
                href={hrefOf(row)}
                scroll={false}
                aria-current={row.id === openId ? 'true' : undefined}
                onClick={event => {
                  if (!isPlainClick(event)) return;
                  event.preventDefault();
                  onOpen(row);
                }}
                className={cn(
                  'flex min-h-11 flex-col justify-center gap-0.5 px-4 py-1.5 text-sm transition-colors',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                  row.id === openId ? 'bg-primary/5' : 'hover:bg-muted/40'
                )}
              >
                <span className="flex min-w-0 items-baseline justify-between gap-2">
                  <span className="truncate font-medium">
                    {row.sender ? addressLabel(row.sender) : t('workbench.mail.unknown_sender')}
                  </span>
                  <time
                    dateTime={row.received_at ?? undefined}
                    className="shrink-0 text-xs tabular-nums text-muted-foreground"
                  >
                    {whenOf(row)}
                  </time>
                </span>
                {row.snippet && (
                  <span className="truncate text-xs text-muted-foreground">{row.snippet}</span>
                )}
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
