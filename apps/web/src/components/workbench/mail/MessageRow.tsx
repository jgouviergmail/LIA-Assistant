'use client';

/**
 * MessageRow — one message of a listing (ADR-369, mock-ups « Main » and
 * « Mobile — mail »).
 *
 * Who, when, what and a line of it; unread in bold with a dot (the dot is
 * never the only carrier: the link names the state); the person's own Gmail
 * labels as chips; a star when starred. The row's link opens the message on
 * the address (`?id=`) — a plain click is taken by the screen so the reader
 * opens without a scroll, a click with a modifier opens a tab as any link. The
 * checkbox selects it for an act on several; below `lg` it is shown only once
 * the person asked to select.
 */
import Link from 'next/link';
import { Star } from 'lucide-react';
import type { MouseEvent } from 'react';

import { Checkbox } from '@/components/ui/checkbox';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { addressLabel, type MailDensity } from '@/lib/workbench/mail';
import type { MailSummary } from '@/lib/workbench/types';

export interface MessageRowProps {
  lng: Language;
  message: MailSummary;
  /** How the list tells when it arrived (`receivedLabel`), or null. */
  when: string | null;
  open: boolean;
  selected: boolean;
  /** The checkbox is drawn (from `lg` always, below once selection is asked). */
  selectable: boolean;
  density: MailDensity;
  /** A label's name, for the chips; undefined for one the pane does not list. */
  labelName: (labelId: string) => string | undefined;
  href: string;
  onOpen: (message: MailSummary) => void;
  onToggle: (message: MailSummary) => void;
  linkRef: (messageId: string, link: HTMLAnchorElement | null) => void;
}

/** A plain primary click — the one the screen takes; any modifier is the browser's. */
function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

export function MessageRow({
  lng,
  message,
  when,
  open,
  selected,
  selectable,
  density,
  labelName,
  href,
  onOpen,
  onToggle,
  linkRef,
}: MessageRowProps) {
  const { t } = useTranslation(lng);
  const sender = message.sender ? addressLabel(message.sender) : t('workbench.mail.unknown_sender');
  const subject = message.subject || t('workbench.mail.no_subject');
  const compact = density === 'compact';
  const shown: RowShown = { message, sender, subject, when, unread: !message.is_read };
  return (
    <li className={rowClass(open, selected, compact)}>
      {selectable && (
        <Checkbox
          checked={selected}
          onChange={() => onToggle(message)}
          aria-label={t('workbench.mail.select_message', { sender, subject })}
          className={compact ? 'mt-1' : 'mt-1.5'}
        />
      )}
      <span
        aria-hidden="true"
        className={cn('mt-2 h-2 w-2 shrink-0 rounded-full', shown.unread && 'bg-primary')}
      />
      <Link
        ref={link => linkRef(message.id, link)}
        href={href}
        scroll={false}
        data-mail-row=""
        aria-current={open ? 'true' : undefined}
        onClick={event => {
          if (!isPlainClick(event)) return;
          event.preventDefault();
          onOpen(message);
        }}
        className={cn(
          'min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          compact ? 'flex items-center gap-3' : 'flex flex-col gap-0.5'
        )}
      >
        {shown.unread && <span className="sr-only">{t('workbench.mail.unread')}</span>}
        {compact ? (
          <CompactLine shown={shown} />
        ) : (
          <ComfortableLines shown={shown} chips={chipsOf(message, labelName)} />
        )}
      </Link>
      {message.is_starred && (
        <Star
          className={cn('h-4 w-4 shrink-0 fill-current text-primary', compact ? 'mt-0.5' : 'mt-1')}
          role="img"
          aria-label={t('workbench.mail.starred')}
        />
      )}
    </li>
  );
}

/** What a row says, resolved once for both densities. */
interface RowShown {
  message: MailSummary;
  sender: string;
  subject: string;
  when: string | null;
  unread: boolean;
}

function rowClass(open: boolean, selected: boolean, compact: boolean): string {
  let tone = 'hover:bg-muted/40';
  if (open) tone = 'bg-primary/5';
  else if (selected) tone = 'bg-muted/60';
  return cn(
    'flex items-start gap-3 border-b px-4 transition-colors',
    compact ? 'py-2' : 'py-3',
    tone
  );
}

/** The person's labels the pane names, as chips. */
function chipsOf(
  message: MailSummary,
  labelName: (labelId: string) => string | undefined
): { id: string; name: string }[] {
  return message.label_ids.flatMap(id => {
    const name = labelName(id);
    return name ? [{ id, name }] : [];
  });
}

function When({ shown, strong }: { shown: RowShown; strong: boolean }) {
  if (!shown.when) return null;
  return (
    <time
      dateTime={shown.message.received_at ?? undefined}
      className={cn(
        'shrink-0 text-xs tabular-nums',
        strong ? 'font-semibold text-primary' : 'text-muted-foreground'
      )}
    >
      {shown.when}
    </time>
  );
}

/** Three lines and the chips: who and when, what, a line of it. */
function ComfortableLines({
  shown,
  chips,
}: {
  shown: RowShown;
  chips: { id: string; name: string }[];
}) {
  const { message, sender, subject, unread } = shown;
  return (
    <>
      <span className="flex min-w-0 items-baseline justify-between gap-2">
        <span className={cn('truncate', unread && 'font-semibold')}>{sender}</span>
        <When shown={shown} strong={unread} />
      </span>
      <span className={cn('min-w-0 truncate', unread && 'font-semibold')}>{subject}</span>
      {message.snippet && (
        <span className="truncate text-sm text-muted-foreground">{message.snippet}</span>
      )}
      {chips.length > 0 && (
        <span className="mt-1 flex flex-wrap gap-1">
          {chips.map(chip => (
            <span
              key={chip.id}
              className="inline-flex h-5 items-center rounded-full bg-primary/10 px-2 text-[11px] font-semibold text-primary"
            >
              {chip.name}
            </span>
          ))}
        </span>
      )}
    </>
  );
}

/** One line: who, what — a line of it, when. */
function CompactLine({ shown }: { shown: RowShown }) {
  const { message, sender, subject, unread } = shown;
  return (
    <>
      <span className={cn('w-40 shrink-0 truncate', unread && 'font-semibold')}>{sender}</span>
      <span className="min-w-0 flex-1 truncate">
        <span className={cn(unread && 'font-semibold')}>{subject}</span>
        {message.snippet && <span className="text-muted-foreground"> — {message.snippet}</span>}
      </span>
      <When shown={shown} strong={false} />
    </>
  );
}
