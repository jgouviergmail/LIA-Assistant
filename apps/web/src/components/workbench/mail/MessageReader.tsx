'use client';

/**
 * MessageReader — one message, read (ADR-369, mock-ups « Main » and
 * « Mobile — message »).
 *
 * The subject, who sent it to whom, when (in the account's zone), the
 * person's labels, the message — its original layout in a sandboxed frame on
 * its own paper when it has one (D3; its text a click away), else the provider's
 * clean text in the theme's colours — and the files. What the list it came from
 * says of leaving it sits under the sender. The
 * toolbar answers, forwards, marks unread or read and labels (Gmail); « … » archives,
 * moves, reports spam and takes it to another tool; like every bar it ends on the
 * trash, then the question to LIA.
 * On a phone the answers end the page, each on its own line and the whole width, and stand
 * again above the message, for a pane taller than the screen; beyond, they sit in a bar under
 * the message until the toolbar has the room. Under the toolbar stands what
 * the screen passes as the conversation: outside the message, it stays while the next
 * one loads.
 * Below `xl` the reader replaces the list, so its first control leads back to
 * the folder, and it takes the focus when it opens below `lg`.
 *
 * A passage of the text can be acted on with LIA (owner, 2026-11-07): selected in the text view,
 * it opens the shared selection bubble, which answers beside it or proposes a native form. The original layout stays in its isolated frame, whose selection the page
 * cannot read: « Act on a passage », under « Ask LIA », turns it to the text and says what to do.
 */
import {
  Archive,
  ArchiveRestore,
  CalendarPlus,
  ChevronLeft,
  FolderInput,
  Forward,
  Inbox,
  ListPlus,
  Mail,
  MailOpen,
  MoreHorizontal,
  OctagonAlert,
  Printer,
  Reply,
  ReplyAll,
  Star,
  TextSelect,
  Trash2,
  UserPlus,
  X,
  type LucideIcon,
} from '@/lib/icons';
import dynamic from 'next/dynamic';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/ui/empty-state';
import { LinkedText } from '@/components/ui/linked-text';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { ProposedEvent, ProposedTask } from '@/lib/workbench/assist';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { isAndroidShell, shellCapability } from '@/lib/native/shell';
import {
  addressLabel,
  initials,
  receivedFull,
  type MailMoves,
  type MailSendAct,
} from '@/lib/workbench/mail';
import type {
  MailAddress,
  MailAttachment,
  MailFolder,
  MailHtml,
  MailInlineImage,
  MailInlineImages,
  MailMessage,
  MailUnsubscribe,
} from '@/lib/workbench/types';

import { askAct, BarAct, type AssistOffer, type DetailDeed } from '../DetailBar';
import { useAssistBounds } from '../WorkbenchShell';
import { AttachmentList } from './AttachmentList';
import { LabelMenu } from './LabelMenu';
import type { MailBulkAct } from './MailSelectionBar';

// The original-layout reader parses an inert document with browser DOM APIs.
const AuthoredHtmlFrame = dynamic(
  () => import('../AuthoredHtmlFrame').then(module => module.AuthoredHtmlFrame),
  {
    ssr: false,
  }
);

const NO_IMAGES: readonly MailInlineImage[] = [];

/** Which act of the reader is on its way, if any. */
export type ReaderAct = MailBulkAct;

export interface MessageReaderProps {
  lng: Language;
  message: MailMessage | undefined;
  loading: boolean;
  error: unknown;
  /** Its original layout, once read (its `html` is null when it has none). */
  original: MailHtml | undefined;
  /** The original layout could not be read: the text shows, and says so. */
  originalFailed: boolean;
  /** The account's zone (its days and hours are the ones told). */
  zone: string | undefined;
  /** The open folder's name, for the way back. */
  backLabel: string;
  /** The person's labels where the provider has labels; undefined elsewhere. */
  labels: readonly MailFolder[] | undefined;
  downloadMax: number;
  /** The drive an attachment can be kept on, when one is ready. */
  drive?: { provider: string | null };
  busy: ReaderAct | null;
  focusOnOpen: boolean;
  onClose: () => void;
  onRetry: () => void;
  onReply: (all: boolean) => void;
  onForward: () => void;
  onToggleRead: (read: boolean) => void;
  onToggleStar: (starred: boolean) => void;
  /** What the folder offers (`movesFrom`). */
  moves: MailMoves;
  onSend: (act: MailSendAct) => void;
  /** Opens the folder picker. */
  onMove: () => void;
  onForever: () => void;
  onLabels: (add: string[], remove: string[]) => void;
  /** Where the message can go from here; a tool that is not ready is left out. */
  bridges: MessageBridges;
  /** What LIA can do on it, under the question's icon. */
  assist?: AssistOffer;
  /** What LIA answered, first in the reader. */
  assistPanel?: ReactNode;
  /** What LIA can do on one of its files. */
  attachmentLines?: (attachment: MailAttachment, name: string) => readonly DetailDeed[];
  /** The images it carries, once read. */
  inline: MailInlineImages | undefined;
  /** How it says it can be left, once read. */
  leaving: MailUnsubscribe | undefined;
  onUnsubscribe: () => void;
  /** Its text on paper, where the page has a printer dialog. */
  onPrint?: () => void;
  /** What was said around it. */
  conversation?: ReactNode;
}

/** What LIA read of a task in a message: its title at least. */
export type MessageTask = Pick<ProposedTask, 'title'> & Partial<ProposedTask>;

/** The ways out of a message, each given the message. */
export interface MessageBridges {
  /** A task named after the message, or after what LIA read in it. */
  toTask?: (message: MailMessage, task?: MessageTask) => void;
  /** An event named after the message, or the one LIA read in it. */
  toEvent?: (message: MailMessage, event?: ProposedEvent) => void;
  toContact?: (message: MailMessage) => void;
  ask: (message: MailMessage) => void;
}

function names(addresses: readonly MailAddress[]): string {
  return addresses.map(addressLabel).join(', ');
}

/** A guard, not the attribute: `aria-disabled` keeps the focus where it is. */
function whileIdle(busy: ReaderAct | null, act: () => void) {
  return () => {
    if (busy === null) act();
  };
}

/** How the text view of the open message was asked for: its swap, or a passage to act on. */
interface TextView {
  asText: boolean;
  /** Asked for a passage: the text says what to do with one. */
  hinted: boolean;
  setAsText: (asText: boolean) => void;
  /** « Ask LIA », with « Act on a passage » where the original layout hides the text. */
  offer: AssistOffer | undefined;
}

/**
 * The text view of the open message, kept by its id: another message opens on its own layout.
 *
 * @returns The view, and what « Ask LIA » offers on it.
 */
function useTextView(props: MessageReaderProps): TextView {
  const { lng, message, original, assist } = props;
  const { t } = useTranslation(lng);
  const bounds = useAssistBounds();
  const [view, setView] = useState<{ id: string; hinted: boolean } | null>(null);
  const asText = message !== undefined && view?.id === message.id;
  const setAsText = (next: boolean) =>
    setView(next && message ? { id: message.id, hinted: false } : null);
  const hidden = message !== undefined && Boolean(original?.html) && !asText;
  const actOn: DetailDeed | null =
    bounds && hidden && assist
      ? {
          label: t('workbench.assist.passage.act_on'),
          icon: TextSelect,
          onSelect: () => setView({ id: message.id, hinted: true }),
        }
      : null;
  return {
    asText,
    hinted: asText && view?.hinted === true,
    setAsText,
    offer: actOn && assist ? { ...assist, lines: [...assist.lines, actOn] } : assist,
  };
}

export function MessageReader(props: MessageReaderProps) {
  const { lng, message, loading, error, backLabel, focusOnOpen, onClose, onRetry, conversation } =
    props;
  const { t } = useTranslation(lng);
  const back = useRef<HTMLButtonElement>(null);
  const view = useTextView(props);

  useEffect(() => {
    if (focusOnOpen) back.current?.focus();
  }, [focusOnOpen]);

  let content;
  // Keyed: each message starts on its own layout, never on the last one's text view.
  if (message) {
    content = (
      <ReaderBody
        key={message.id}
        {...props}
        message={message}
        asText={view.asText}
        hinted={view.hinted}
        onAsText={view.setAsText}
      />
    );
  } else if (loading) content = <ReaderSkeleton />;
  else {
    const refusal = workbenchRefusal(error);
    content = (
      <EmptyState
        description={refusal ? t(refusal.key, refusal.values) : t('workbench.mail.read_failed')}
        action={{ label: t('workbench.states.retry'), onClick: onRetry }}
      />
    );
  }

  return (
    <article
      aria-label={message?.subject || t('workbench.mail.reader_title')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="flex items-center gap-1 border-b px-2 py-1.5">
        <Button
          ref={back}
          variant="ghost"
          onClick={onClose}
          className="min-w-0 gap-1 px-2 xl:hidden"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          <span className="min-w-0 max-w-[12rem] truncate">{backLabel}</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="hidden xl:inline-flex"
          aria-label={t('workbench.mail.close_message')}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
        {message && <ReaderToolbar {...props} assist={view.offer} message={message} />}
      </div>
      {conversation}
      {content}
    </article>
  );
}

/** What sends the message out of its folder, from « … »; each acts once the last one is done. */
function FolderLines({
  lng,
  busy,
  moves,
  onSend,
  onMove,
}: Pick<MessageReaderProps, 'lng' | 'busy' | 'moves' | 'onSend' | 'onMove'>) {
  const { t } = useTranslation(lng);
  return (
    <>
      {moves.archive && (
        <DropdownMenuItem onSelect={whileIdle(busy, () => onSend('archive'))}>
          <Archive className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.archive')}
        </DropdownMenuItem>
      )}
      {moves.move && (
        <DropdownMenuItem onSelect={whileIdle(busy, onMove)}>
          <FolderInput className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.move_to')}
        </DropdownMenuItem>
      )}
      {moves.spam && (
        <DropdownMenuItem onSelect={whileIdle(busy, () => onSend('spam'))}>
          <OctagonAlert className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.report_spam')}
        </DropdownMenuItem>
      )}
    </>
  );
}

/** Whether « … » has a line: the trash and the spam send nowhere from it, and the other tools
 * and the printer may be missing. A menu of nothing would open on nothing. */
function listsAnything({
  message,
  bridges,
  onPrint,
  moves,
}: Pick<MessageReaderProps, 'bridges' | 'onPrint' | 'moves'> & {
  message: MailMessage;
}): boolean {
  const { toTask, toEvent, toContact } = bridges;
  const elsewhere = toTask || toEvent || onPrint || (toContact && message.sender);
  return moves.archive || moves.move || moves.spam || Boolean(elsewhere);
}

/** What is less common: leaving the folder, another tool, the printer. */
function BridgeMenu({
  lng,
  message,
  bridges,
  onPrint,
  busy,
  moves,
  onSend,
  onMove,
}: Pick<
  MessageReaderProps,
  'lng' | 'bridges' | 'onPrint' | 'busy' | 'moves' | 'onSend' | 'onMove'
> & { message: MailMessage }) {
  const { t } = useTranslation(lng);
  const { toTask, toEvent, toContact } = bridges;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          isLoading={busy === 'archive' || busy === 'spam'}
          aria-label={t('workbench.mail.more_actions')}
        >
          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <FolderLines lng={lng} busy={busy} moves={moves} onSend={onSend} onMove={onMove} />
        {toTask && (
          <DropdownMenuItem onSelect={() => toTask(message)}>
            <ListPlus className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.to_task')}
          </DropdownMenuItem>
        )}
        {toEvent && (
          <DropdownMenuItem onSelect={() => toEvent(message)}>
            <CalendarPlus className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.to_event')}
          </DropdownMenuItem>
        )}
        {toContact && message.sender && (
          <DropdownMenuItem onSelect={() => toContact(message)}>
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.to_contact')}
          </DropdownMenuItem>
        )}
        {onPrint && (
          <DropdownMenuItem onSelect={onPrint}>
            <Printer className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.print')}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ReaderToolbar({
  lng,
  message,
  labels,
  busy,
  onReply,
  onForward,
  onToggleRead,
  onToggleStar,
  moves,
  onSend,
  onMove,
  onForever,
  onLabels,
  bridges,
  assist,
  onPrint,
}: MessageReaderProps & { message: MailMessage }) {
  const { t } = useTranslation(lng);
  return (
    <span data-testid="reader-acts" className="ml-auto flex shrink-0 items-center gap-0.5">
      {/* From 2xl the reader is wide enough for the answers in words; below, they sit in the bar under the message. */}
      <span className="hidden items-center gap-0.5 2xl:flex">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => onReply(false)}>
          <Reply className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.reply')}
        </Button>
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => onReply(true)}>
          <ReplyAll className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.reply_all')}
        </Button>
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={onForward}>
          <Forward className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.forward')}
        </Button>
      </span>
      <Button
        variant="ghost"
        size="icon"
        isLoading={busy === 'read'}
        aria-disabled={(busy !== null && busy !== 'read') || undefined}
        onClick={whileIdle(busy, () => onToggleRead(!message.is_read))}
        aria-label={t(message.is_read ? 'workbench.mail.mark_unread' : 'workbench.mail.mark_read')}
      >
        {message.is_read ? (
          <Mail className="h-4 w-4" aria-hidden="true" />
        ) : (
          <MailOpen className="h-4 w-4" aria-hidden="true" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        isLoading={busy === 'star'}
        aria-disabled={(busy !== null && busy !== 'star') || undefined}
        onClick={whileIdle(busy, () => onToggleStar(!message.is_starred))}
        aria-label={t(message.is_starred ? 'workbench.mail.unstar' : 'workbench.mail.star')}
      >
        <Star
          className={cn('h-4 w-4', message.is_starred && 'fill-current text-primary')}
          aria-hidden="true"
        />
      </Button>
      {labels && (
        <LabelMenu
          lng={lng}
          labels={labels}
          messages={[message]}
          busy={busy !== null}
          iconOnly
          onApply={onLabels}
        />
      )}
      <ReaderWaysBack lng={lng} busy={busy} moves={moves} onSend={onSend} />
      {listsAnything({ message, bridges, onPrint, moves }) && (
        <BridgeMenu
          lng={lng}
          message={message}
          bridges={bridges}
          onPrint={onPrint}
          busy={busy}
          moves={moves}
          onSend={onSend}
          onMove={onMove}
        />
      )}
      <ReaderDeletions lng={lng} busy={busy} moves={moves} onSend={onSend} onForever={onForever} />
      <BarAct act={askAct(t('workbench.ask.label'), () => bridges.ask(message), assist)} />
    </span>
  );
}

/** The one press that takes the open message back out of the trash or the spam. */
function ReaderWaysBack({
  lng,
  busy,
  moves,
  onSend,
}: Pick<MessageReaderProps, 'lng' | 'busy' | 'moves' | 'onSend'>) {
  const { t } = useTranslation(lng);
  return (
    <>
      {waysBack(moves).map(({ act, key, icon: Icon }) => (
        <Button
          key={act}
          variant="ghost"
          size="icon"
          isLoading={busy === act}
          aria-disabled={(busy !== null && busy !== act) || undefined}
          onClick={whileIdle(busy, () => onSend(act))}
          aria-label={t(key)}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </Button>
      ))}
    </>
  );
}

/** What deletes the open message: its trash, or its end for good. */
function ReaderDeletions({
  lng,
  busy,
  moves,
  onSend,
  onForever,
}: Pick<MessageReaderProps, 'lng' | 'busy' | 'moves' | 'onSend' | 'onForever'>) {
  const { t } = useTranslation(lng);
  return (
    <>
      {!moves.restore && (
        <Button
          variant="ghost"
          size="icon"
          isLoading={busy === 'trash'}
          aria-disabled={(busy !== null && busy !== 'trash') || undefined}
          onClick={whileIdle(busy, () => onSend('trash'))}
          className="text-destructive hover:text-destructive"
          aria-label={t('workbench.mail.trash')}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      {moves.forever && (
        <Button
          variant="ghost"
          size="icon"
          isLoading={busy === 'forever'}
          aria-disabled={(busy !== null && busy !== 'forever') || undefined}
          onClick={whileIdle(busy, onForever)}
          className="text-destructive hover:text-destructive"
          aria-label={t('workbench.mail.delete_forever')}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
    </>
  );
}

/** The ways back the folder offers, as the toolbar draws them. */
function waysBack(moves: MailMoves): { act: MailSendAct; key: string; icon: LucideIcon }[] {
  const all: { act: MailSendAct; key: string; icon: LucideIcon; on: boolean }[] = [
    { act: 'restore', key: 'workbench.mail.restore', icon: ArchiveRestore, on: moves.restore },
    { act: 'not_spam', key: 'workbench.mail.not_spam', icon: Inbox, on: moves.notSpam },
  ];
  return all.filter(button => button.on);
}

/** The way out the message names, the plainest first: one click, its page, a message. */
function Unsubscribe({
  lng,
  leaving,
  onUnsubscribe,
}: {
  lng: Language;
  leaving: MailUnsubscribe | undefined;
  onUnsubscribe: () => void;
}) {
  const { t } = useTranslation(lng);
  if (!leaving || (!leaving.web_url && !leaving.mail_to)) return null;
  if (leaving.web_url && !leaving.one_click) {
    return (
      <a
        href={leaving.web_url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-primary underline-offset-4 hover:underline"
      >
        {t('workbench.mail.unsubscribe')}
      </a>
    );
  }
  return (
    <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onUnsubscribe}>
      {t('workbench.mail.unsubscribe')}
    </Button>
  );
}

function ReaderBody({
  lng,
  message,
  original,
  originalFailed,
  zone,
  labels,
  downloadMax,
  drive,
  onReply,
  onForward,
  inline,
  leaving,
  onUnsubscribe,
  assistPanel,
  attachmentLines,
  asText,
  hinted,
  onAsText,
}: MessageReaderProps & { message: MailMessage } & BodyView) {
  const { t } = useTranslation(lng);
  const sender = message.sender;
  const chips = (labels ?? []).filter(label => message.label_ids.includes(label.id));
  const when = receivedFull(message.received_at, zone, lng);
  return (
    <>
      <div className="@container min-h-0 flex-1 space-y-4 overflow-y-auto p-4 max-sm:flex max-sm:flex-col max-sm:[&>*]:shrink-0">
        {assistPanel}
        <h2 className="text-lg font-bold leading-snug text-foreground">
          {message.subject || t('workbench.mail.no_subject')}
        </h2>
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-bold text-primary"
          >
            {initials(sender)}
          </span>
          <div className="min-w-0 flex-1 text-sm">
            <p className="truncate">
              <span className="font-semibold">
                {sender ? addressLabel(sender) : t('workbench.mail.unknown_sender')}
              </span>
              {sender?.name && sender.address && (
                <span className="text-muted-foreground"> &lt;{sender.address}&gt;</span>
              )}
            </p>
            {message.to.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {t('workbench.mail.to_line', { names: names(message.to) })}
              </p>
            )}
            {message.cc.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {t('workbench.mail.cc_line', { names: names(message.cc) })}
              </p>
            )}
            <Unsubscribe lng={lng} leaving={leaving} onUnsubscribe={onUnsubscribe} />
          </div>
          {when && (
            <time
              dateTime={message.received_at ?? undefined}
              className="shrink-0 text-xs text-muted-foreground"
            >
              {when}
            </time>
          )}
        </div>
        {chips.length > 0 && (
          <ul aria-label={t('workbench.mail.labels_title')} className="flex flex-wrap gap-1">
            {chips.map(label => (
              <li
                key={label.id}
                className="inline-flex h-6 items-center rounded-full bg-primary/10 px-2.5 text-xs font-semibold text-primary"
              >
                {label.name}
              </li>
            ))}
          </ul>
        )}
        <div
          role="group"
          aria-label={t('workbench.mail.answer_bar')}
          className="rounded-md border lg:hidden"
        >
          <AnswerButtons lng={lng} onReply={onReply} onForward={onForward} />
        </div>
        <MessageBody
          lng={lng}
          text={message.body}
          original={original}
          inline={inline}
          originalFailed={originalFailed}
          asText={asText}
          hinted={hinted}
          onAsText={onAsText}
        />
        <AttachmentList
          lng={lng}
          messageId={message.id}
          attachments={message.attachments}
          maxBytes={downloadMax}
          drive={drive}
          lines={attachmentLines}
        />
        <AnswerLines lng={lng} onReply={onReply} onForward={onForward} />
      </div>
      <nav
        aria-label={t('workbench.mail.answer_bar')}
        className="hidden border-t bg-card sm:block 2xl:hidden"
      >
        <AnswerButtons lng={lng} onReply={onReply} onForward={onForward} />
      </nav>
    </>
  );
}

/** Where a phone's page ends: the three answers, one per line, the whole width. */
function AnswerLines({
  lng,
  onReply,
  onForward,
}: Pick<MessageReaderProps, 'lng' | 'onReply' | 'onForward'>) {
  const { t } = useTranslation(lng);
  return (
    <div
      role="group"
      aria-label={t('workbench.mail.answer_bar')}
      className="grid gap-2 max-sm:mt-auto sm:hidden"
    >
      <Button variant="outline" onClick={() => onReply(false)}>
        <Reply className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.reply')}
      </Button>
      <Button variant="outline" onClick={() => onReply(true)}>
        <ReplyAll className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.reply_all')}
      </Button>
      <Button variant="outline" onClick={onForward}>
        <Forward className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.forward')}
      </Button>
    </div>
  );
}

/** The three answers, each its icon above its word. */
function AnswerButtons({
  lng,
  onReply,
  onForward,
}: Pick<MessageReaderProps, 'lng' | 'onReply' | 'onForward'>) {
  const { t } = useTranslation(lng);
  return (
    <div className="grid grid-cols-3">
      <AnswerButton label={t('workbench.mail.reply')} onClick={() => onReply(false)}>
        <Reply className="h-5 w-5 text-primary" aria-hidden="true" />
      </AnswerButton>
      <AnswerButton label={t('workbench.mail.reply_all')} onClick={() => onReply(true)}>
        <ReplyAll className="h-5 w-5 text-primary" aria-hidden="true" />
      </AnswerButton>
      <AnswerButton label={t('workbench.mail.forward')} onClick={onForward}>
        <Forward className="h-5 w-5 text-primary" aria-hidden="true" />
      </AnswerButton>
    </div>
  );
}

/** The text view, as the reader keeps it. */
interface BodyView {
  asText: boolean;
  /** It was asked for a passage: the text says what to do with one. */
  hinted: boolean;
  onAsText: (asText: boolean) => void;
}

interface MessageBodyProps extends BodyView {
  lng: Language;
  text: string;
  original: MailHtml | undefined;
  originalFailed: boolean;
  inline: MailInlineImages | undefined;
}

/**
 * Whether the reader says the links open from the text: measured, an Android shell older than
 * its `frameLinks` capability opens nothing from a sandboxed frame.
 */
function useLinksInText(): boolean {
  const [frameLinks, setFrameLinks] = useState(false);
  useEffect(() => {
    void shellCapability('frameLinks').then(setFrameLinks);
  }, []);
  return isAndroidShell() && !frameLinks;
}

/** The original layout when the message has one, else (or on demand) its text. */
function MessageBody({
  lng,
  text,
  original,
  originalFailed,
  inline,
  asText,
  hinted,
  onAsText,
}: MessageBodyProps) {
  const { t } = useTranslation(lng);
  // Above the frame, so a look at the text does not take back what the reader asked for.
  const [images, setImages] = useState(false);
  const linksInText = useLinksInText();
  const html = original?.html ?? null;
  const swap = (label: string, next: boolean, place?: string) => (
    <Button
      variant="link"
      size="sm"
      className={cn('h-auto p-0 text-xs', place)}
      onClick={() => onAsText(next)}
    >
      {label}
    </Button>
  );
  if (html !== null && !asText) {
    return (
      <div className="space-y-2">
        {linksInText && (
          <p className="text-xs text-muted-foreground">{t('workbench.mail.links_in_text')}</p>
        )}
        {original?.truncated && (
          <p className="text-xs text-muted-foreground">{t('workbench.mail.html_truncated')}</p>
        )}
        <AuthoredHtmlFrame
          lng={lng}
          html={html}
          title={t('workbench.mail.html_frame_title')}
          images={images}
          onShowImages={() => setImages(true)}
          inline={inline?.images ?? NO_IMAGES}
          lead={swap(
            t('workbench.mail.show_text'),
            true,
            'col-start-1 justify-self-start text-left'
          )}
        />
        {Boolean(inline?.skipped) && (
          <p className="text-xs text-muted-foreground">
            {t('workbench.mail.inline_skipped', { count: inline?.skipped })}
          </p>
        )}
      </div>
    );
  }
  return (
    <MessageText
      lng={lng}
      text={text}
      hinted={hinted}
      back={html !== null ? swap(t('workbench.mail.show_original'), false) : null}
      failed={originalFailed}
    />
  );
}

/**
 * A message's text, a passage of which can be acted on with LIA (the selection bubble). Asked for
 * a passage, it says what to do with one and takes the focus, where the selection is made.
 */
function MessageText({
  lng,
  text,
  hinted,
  back,
  failed,
}: {
  lng: Language;
  text: string;
  hinted: boolean;
  /** The way back to the original layout, where there is one. */
  back: ReactNode;
  /** The original layout could not be read. */
  failed: boolean;
}) {
  const { t } = useTranslation(lng);
  const scope = useRef<HTMLDivElement>(null);
  const owner = useId();
  useEffect(() => {
    if (hinted) scope.current?.focus();
  }, [hinted]);
  return (
    <div className="space-y-2">
      {hinted && (
        <p className="text-xs text-muted-foreground">{t('workbench.assist.passage.act_on_hint')}</p>
      )}
      <div
        ref={scope}
        tabIndex={-1}
        data-selection-scope="workbench"
        data-selection-owner={owner}
        className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground outline-none"
      >
        <LinkedText text={text} />
      </div>

      {back}
      {failed && <p className="text-xs text-muted-foreground">{t('workbench.mail.html_failed')}</p>}
    </div>
  );
}

function AnswerButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-14 flex-col items-center justify-center gap-1 text-xs font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
    >
      {children}
      {label}
    </button>
  );
}

function ReaderSkeleton() {
  return (
    <div className="space-y-3 p-4" aria-busy="true">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
