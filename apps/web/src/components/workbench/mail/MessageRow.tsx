'use client';

/**
 * MessageRow — one message of a listing (ADR-369, mock-ups « Main » and
 * « Mobile — mail »).
 *
 * Who, when, what and a line of it; unread in bold with a dot before the sender
 * (the dot is never the only carrier: the link names the state); the person's own
 * Gmail labels as chips; where it stands in its conversation when something happened —
 * answered, an answer drafted, a reply received (ADR-379); a paperclip when it carries
 * files, a star when starred and its acts folded: laid out, the act's own star says it.
 * The row's link opens the
 * message on
 * the address (`?id=`) — a plain click is taken by the screen so the reader
 * opens without a scroll, a click with a modifier opens a tab as any link. The
 * checkbox selects it for an act on several, with Shift every message since the
 * last one ticked; below `lg` it is shown only once the person asked to select.
 * Its own acts never need a pointer to reveal them (`RowActions`). Laid out in full,
 * they start at the left of the line of the checkbox, above the sender, what the row
 * says of itself after them, and leave the lines of the message the whole width; a
 * row narrowed by the open reader or a phone folds them in a menu at its end, and one
 * line keeps them at its end too. From `lg`, with a
 * mouse, the row itself can be dragged to a folder of the pane: only its pointer
 * listeners, never dnd-kit's button role, which would nest the link; the keyboard
 * and the phone have « Move to ».
 */
import { useDraggable } from '@dnd-kit/core';
import Link from 'next/link';
import {
  Archive,
  ArchiveRestore,
  FolderInput,
  Inbox,
  Mail,
  MailOpen,
  MessagesSquare,
  OctagonAlert,
  Paperclip,
  Star,
  Trash2,
} from '@/lib/icons';
import type { CSSProperties, MouseEvent } from 'react';

import { Checkbox } from '@/components/ui/checkbox';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import {
  addressLabel,
  type MailDensity,
  type MailMoves,
  type MailSendAct,
} from '@/lib/workbench/mail';
import type { MailReplyMark, MailSummary } from '@/lib/workbench/types';

import { ReplyMarkIcon } from './ReplyMarkIcon';

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
  /** The row is narrowed by the reader beside it: its acts fold in a menu. */
  narrow: boolean;
  /** A word on the row's kind, beside its labels. */
  note?: string;
  /** A label's name, for the chips; undefined for one the pane does not list. */
  labelName: (labelId: string) => string | undefined;
  href: string;
  onOpen: (message: MailSummary) => void;
  /** @param range - Shift was held: a range, not one message. */
  onToggle: (message: MailSummary, range: boolean) => void;
  onRead: (message: MailSummary, read: boolean) => void;
  /** What the folder offers (`movesFrom`). */
  moves: MailMoves;
  onStar: (message: MailSummary, starred: boolean) => void;
  onSend: (message: MailSummary, act: MailSendAct) => void;
  /** Opens the folder picker. */
  onMove: (message: MailSummary) => void;
  onForever: (message: MailSummary) => void;
  /** From `lg`, with a mouse, the row can be dragged to a folder. */
  draggable?: boolean;
  /** The row stands for several messages of a conversation. */
  conversation?: boolean;
  /** Where it stands in its conversation, when something happened (ADR-379). */
  replyMark?: MailReplyMark;
  linkRef: (messageId: string, link: HTMLAnchorElement | null) => void;
}

/** Folded in a menu, the row's marks and acts sit over its first line: the others run on under. */
const OVER_THE_FIRST_LINE = 'absolute right-4 top-1.5';
const OVER_THE_FIRST_LINE_ON_A_PHONE = 'max-sm:absolute max-sm:right-4 max-sm:top-1.5';
/** The room that line leaves them: the menu, and a mark's width each. */
const CLEAR_OF_THE_MARKS = 'pr-[calc(2.5rem+var(--row-marks)*1.75rem)]';
const CLEAR_OF_THE_MARKS_ON_A_PHONE = 'max-sm:pr-[calc(2.5rem+var(--row-marks)*1.75rem)]';

/** Whether Shift was held: a checkbox's change comes from its click. */
function shifted(event: Event): boolean {
  return event instanceof MouseEvent && event.shiftKey;
}

/** A plain primary click — the one the screen takes; any modifier is the browser's. */
export function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

export function MessageRow({
  lng,
  message,
  note,
  when,
  open,
  selected,
  selectable,
  density,
  narrow,
  labelName,
  href,
  onOpen,
  onToggle,
  onRead,
  moves,
  onStar,
  onSend,
  onMove,
  onForever,
  draggable = false,
  conversation = false,
  replyMark,
  linkRef,
}: MessageRowProps) {
  const { t } = useTranslation(lng);
  const sender = message.sender ? addressLabel(message.sender) : t('workbench.mail.unknown_sender');
  const subject = message.subject || t('workbench.mail.no_subject');
  const compact = density === 'compact';
  const roomy = !narrow;
  const stacked = roomy && !compact;
  const {
    setNodeRef: setRow,
    listeners: carry,
    isDragging: carried,
  } = useDraggable({ id: message.id, disabled: !draggable });
  const shown: RowShown = { message, sender, subject, when, unread: !message.is_read };
  const actions = rowActions(message, subject, moves, t, {
    onRead,
    onStar,
    onSend,
    onMove,
    onForever,
  });
  return (
    <li
      ref={setRow}
      {...carry}
      className={cn(rowClass(open, selected, compact, roomy, stacked), carried && 'opacity-50')}
    >
      {selectable && (
        <Checkbox
          checked={selected}
          onChange={event => onToggle(message, shifted(event.nativeEvent))}
          aria-label={t('workbench.mail.select_message', { sender, subject })}
          className={cn(compact ? 'mt-1' : 'mt-1.5', roomy && 'sm:mt-0')}
        />
      )}
      <Link
        ref={link => linkRef(message.id, link)}
        href={href}
        scroll={false}
        data-mail-row=""
        draggable={draggable ? false : undefined}
        aria-current={open ? 'true' : undefined}
        onClick={event => {
          if (!isPlainClick(event)) return;
          event.preventDefault();
          onOpen(message);
        }}
        className={linkPlace(compact, stacked)}
      >
        {shown.unread && <span className="sr-only">{t('workbench.mail.unread')}</span>}
        {compact ? (
          <CompactLine shown={shown} />
        ) : (
          <ComfortableLines
            shown={shown}
            chips={[
              ...(note ? [{ id: 'lia-note', name: note }] : []),
              ...chipsOf(message, labelName),
            ]}
            narrow={narrow}
            marks={markCount(message, conversation, replyMark)}
          />
        )}
      </Link>
      <div className={actsPlace(compact, narrow, roomy, stacked)}>
        <RowMarks
          lng={lng}
          message={message}
          compact={compact}
          roomy={roomy}
          stacked={stacked}
          conversation={conversation}
          replyMark={replyMark}
        />
        <RowActions
          actions={actions}
          menuLabel={t('workbench.mail.row_actions', { subject })}
          compact={narrow}
        />
      </div>
    </li>
  );
}

function linkPlace(compact: boolean, stacked: boolean): string {
  return cn(
    'min-w-0 flex-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
    compact ? 'flex items-center gap-3' : 'flex flex-col gap-0.5',
    stacked && 'sm:order-3 sm:basis-full'
  );
}

function actsPlace(compact: boolean, narrow: boolean, roomy: boolean, stacked: boolean): string {
  return cn(
    'flex shrink-0 gap-3',
    compact ? 'items-start' : 'items-center',
    roomy && 'sm:items-center',
    stacked && 'sm:order-2',
    !compact && (narrow ? OVER_THE_FIRST_LINE : OVER_THE_FIRST_LINE_ON_A_PHONE)
  );
}

/** How many marks the row carries (`RowMarks`). */
function markCount(
  message: MailSummary,
  conversation: boolean,
  replyMark: MailReplyMark | undefined
): number {
  return [replyMark, conversation, message.has_attachments, message.is_starred].filter(Boolean)
    .length;
}

/** What the row says of itself: where it stands, its conversation, its files, its star. */
function RowMarks({
  lng,
  message,
  compact,
  roomy,
  stacked,
  conversation,
  replyMark,
}: {
  lng: Language;
  message: MailSummary;
  replyMark: MailReplyMark | undefined;
  compact: boolean;
  /** Laid out at its width: its acts are drawn, the star among them. */
  roomy: boolean;
  /** Its acts stand above the sender, and these marks after them. */
  stacked: boolean;
  conversation: boolean;
}) {
  const { t } = useTranslation(lng);
  const place = cn(compact && 'mt-0.5', roomy && 'sm:mt-0');
  return (
    <span
      className={cn(
        'flex shrink-0 gap-3',
        compact ? 'items-start' : 'items-center',
        roomy && 'sm:items-center',
        stacked && 'sm:order-1'
      )}
    >
      {replyMark && <ReplyMarkIcon lng={lng} mark={replyMark} className={place} />}
      {conversation && (
        <MessagesSquare
          className={cn('h-4 w-4 shrink-0 text-muted-foreground', place)}
          role="img"
          aria-label={t('workbench.mail.in_conversation')}
        />
      )}
      {message.has_attachments && (
        <Paperclip
          className={cn('h-4 w-4 shrink-0 text-muted-foreground', place)}
          role="img"
          aria-label={t('workbench.mail.has_attachments')}
        />
      )}
      {message.is_starred && (
        <Star
          className={cn('h-4 w-4 shrink-0 fill-current text-primary', place, roomy && 'sm:hidden')}
          role="img"
          aria-label={t('workbench.mail.starred')}
        />
      )}
    </span>
  );
}

type RowActs = Pick<MessageRowProps, 'onRead' | 'onStar' | 'onSend' | 'onMove' | 'onForever'>;

/** What the row can do: its read state, its star, then what the folder offers. */
function rowActions(
  message: MailSummary,
  subject: string,
  moves: MailMoves,
  t: (key: string, values?: Record<string, string>) => string,
  { onRead, onStar, onSend, onMove, onForever }: RowActs
): RowAction[] {
  const said = (key: string) => t(key, { subject });
  const all: (RowAction & { on: boolean })[] = [
    {
      key: message.is_read ? 'unread' : 'read',
      label: said(
        message.is_read ? 'workbench.mail.row_mark_unread' : 'workbench.mail.row_mark_read'
      ),
      menuText: t(message.is_read ? 'workbench.mail.mark_unread' : 'workbench.mail.mark_read'),
      icon: message.is_read ? Mail : MailOpen,
      onSelect: () => onRead(message, !message.is_read),
      on: true,
    },
    {
      key: 'star',
      label: said(message.is_starred ? 'workbench.mail.row_unstar' : 'workbench.mail.row_star'),
      menuText: t(message.is_starred ? 'workbench.mail.unstar' : 'workbench.mail.star'),
      icon: Star,
      onSelect: () => onStar(message, !message.is_starred),
      iconClassName: message.is_starred ? '[&>svg]:fill-current text-primary' : undefined,
      on: true,
    },
    {
      key: 'archive',
      label: said('workbench.mail.row_archive'),
      menuText: t('workbench.mail.archive'),
      icon: Archive,
      onSelect: () => onSend(message, 'archive'),
      on: moves.archive,
    },
    {
      key: 'restore',
      label: said('workbench.mail.row_restore'),
      menuText: t('workbench.mail.restore'),
      icon: ArchiveRestore,
      onSelect: () => onSend(message, 'restore'),
      on: moves.restore,
    },
    {
      key: 'not_spam',
      label: said('workbench.mail.row_not_spam'),
      menuText: t('workbench.mail.not_spam'),
      icon: Inbox,
      onSelect: () => onSend(message, 'not_spam'),
      on: moves.notSpam,
    },
    {
      key: 'move',
      label: said('workbench.mail.row_move'),
      menuText: t('workbench.mail.move_to'),
      icon: FolderInput,
      onSelect: () => onMove(message),
      on: moves.move,
    },
    {
      key: 'spam',
      label: said('workbench.mail.row_report_spam'),
      menuText: t('workbench.mail.report_spam'),
      icon: OctagonAlert,
      onSelect: () => onSend(message, 'spam'),
      on: moves.spam,
    },
    {
      key: 'forever',
      label: said('workbench.mail.row_delete_forever'),
      menuText: t('workbench.mail.delete_forever'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => onForever(message),
      on: moves.forever,
    },
    {
      key: 'trash',
      label: said('workbench.mail.row_trash'),
      menuText: t('workbench.mail.trash'),
      icon: Trash2,
      tone: 'destructive',
      onSelect: () => onSend(message, 'trash'),
      on: !moves.restore,
    },
  ];
  return all.filter(action => action.on);
}

/** What a row says, resolved once for both densities. */
interface RowShown {
  message: MailSummary;
  sender: string;
  subject: string;
  when: string | null;
  unread: boolean;
}

function rowClass(
  open: boolean,
  selected: boolean,
  compact: boolean,
  roomy: boolean,
  stacked: boolean
): string {
  let tone = 'hover:bg-muted/40';
  if (open) tone = 'bg-primary/5';
  else if (selected) tone = 'bg-muted/60';
  return cn(
    'relative flex items-start gap-3 border-b px-4 transition-colors',
    compact ? 'py-2' : 'py-3',
    roomy && 'sm:items-center',
    stacked && 'sm:flex-wrap sm:gap-y-1',
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

/** Who sent it, the dot before the name; a column keeps the dot's place for every row. */
function Sender({ shown, column = false }: { shown: RowShown; column?: boolean }) {
  return (
    <span className={cn('truncate', column && 'w-40 shrink-0', shown.unread && 'font-semibold')}>
      {(shown.unread || column) && (
        <span
          aria-hidden="true"
          className={cn(
            'mr-2 inline-block h-2 w-2 rounded-full align-middle',
            shown.unread && 'bg-primary'
          )}
        />
      )}
      <span>{shown.sender}</span>
    </span>
  );
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
  narrow,
  marks,
}: {
  shown: RowShown;
  chips: { id: string; name: string }[];
  narrow: boolean;
  /** How many marks the row carries. */
  marks: number;
}) {
  const { message, subject, unread } = shown;
  return (
    <>
      <span
        style={{ '--row-marks': marks } as CSSProperties}
        className={cn(
          'flex min-w-0 items-baseline justify-between gap-2',
          narrow ? CLEAR_OF_THE_MARKS : CLEAR_OF_THE_MARKS_ON_A_PHONE
        )}
      >
        <Sender shown={shown} />
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
  const { message, subject, unread } = shown;
  return (
    <>
      <Sender shown={shown} column />
      <span className="min-w-0 flex-1 truncate">
        <span className={cn(unread && 'font-semibold')}>{subject}</span>
        {message.snippet && <span className="text-muted-foreground"> — {message.snippet}</span>}
      </span>
      <When shown={shown} strong={false} />
    </>
  );
}
