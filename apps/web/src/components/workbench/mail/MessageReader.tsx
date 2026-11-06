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
 * toolbar answers, forwards, marks unread or read, labels (Gmail) and trashes;
 * on a phone the answers sit in a bar at the bottom, where the thumb is. Under the
 * toolbar stands what the screen passes as the conversation: outside the message,
 * it stays while the next one loads.
 * Below `xl` the reader replaces the list, so its first control leads back to
 * the folder, and it takes the focus when it opens below `lg`.
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
  Sparkles,
  Star,
  Trash2,
  UserPlus,
  X,
  type LucideIcon,
} from 'lucide-react';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState, type ReactNode } from 'react';

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
import { getIntlLocale, type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { isAndroidShell, shellCapability } from '@/lib/native/shell';
import { addressLabel, initials, type MailMoves, type MailSendAct } from '@/lib/workbench/mail';
import type {
  MailAddress,
  MailFolder,
  MailHtml,
  MailInlineImage,
  MailInlineImages,
  MailMessage,
  MailUnsubscribe,
} from '@/lib/workbench/types';

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

/** The ways out of a message, each given the message. */
export interface MessageBridges {
  toTask?: (message: MailMessage) => void;
  toEvent?: (message: MailMessage) => void;
  toContact?: (message: MailMessage) => void;
  ask: (message: MailMessage) => void;
}

function receivedFull(iso: string | null, zone: string | undefined, lng: Language): string {
  if (!iso) return '';
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return '';
  return new Intl.DateTimeFormat(getIntlLocale(lng), {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: zone,
  }).format(instant);
}

function names(addresses: readonly MailAddress[]): string {
  return addresses.map(addressLabel).join(', ');
}

export function MessageReader(props: MessageReaderProps) {
  const { lng, message, loading, error, backLabel, focusOnOpen, onClose, onRetry, conversation } =
    props;
  const { t } = useTranslation(lng);
  const back = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (focusOnOpen) back.current?.focus();
  }, [focusOnOpen]);

  let content;
  // Keyed: each message starts on its own layout, never on the last one's text view.
  if (message) content = <ReaderBody key={message.id} {...props} message={message} />;
  else if (loading) content = <ReaderSkeleton />;
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
        <Button ref={back} variant="ghost" onClick={onClose} className="gap-1 px-2 xl:hidden">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          <span className="max-w-[12rem] truncate">{backLabel}</span>
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
        {message && <ReaderToolbar {...props} message={message} />}
      </div>
      {conversation}
      {content}
    </article>
  );
}

/** Where the message can go: another tool, or a question to LIA. */
function BridgeMenu({
  lng,
  message,
  bridges,
  onPrint,
  moves,
  onSend,
  onMove,
}: {
  lng: Language;
  message: MailMessage;
  bridges: MessageBridges;
  onPrint?: () => void;
  moves: MailMoves;
  onSend: (act: MailSendAct) => void;
  onMove: () => void;
}) {
  const { t } = useTranslation(lng);
  const { toTask, toEvent, toContact, ask } = bridges;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('workbench.mail.more_actions')}>
          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
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
        {moves.move && (
          <DropdownMenuItem className="sm:hidden" onSelect={onMove}>
            <FolderInput className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.move_to')}
          </DropdownMenuItem>
        )}
        {moves.spam && (
          <DropdownMenuItem className="sm:hidden" onSelect={() => onSend('spam')}>
            <OctagonAlert className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.report_spam')}
          </DropdownMenuItem>
        )}
        {onPrint && (
          <DropdownMenuItem onSelect={onPrint}>
            <Printer className="h-4 w-4" aria-hidden="true" />
            {t('workbench.mail.print')}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => ask(message)}>
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {t('workbench.ask.label')}
        </DropdownMenuItem>
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
  onPrint,
}: MessageReaderProps & { message: MailMessage }) {
  const { t } = useTranslation(lng);
  // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
  const guarded = (act: () => void) => () => {
    if (busy === null) act();
  };
  return (
    <span className="ml-auto flex items-center gap-0.5">
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
        onClick={guarded(() => onToggleRead(!message.is_read))}
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
        onClick={guarded(() => onToggleStar(!message.is_starred))}
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
      <ReaderMoves
        lng={lng}
        busy={busy}
        moves={moves}
        onSend={onSend}
        onMove={onMove}
        onForever={onForever}
      />
      <BridgeMenu
        lng={lng}
        message={message}
        bridges={bridges}
        onPrint={onPrint}
        moves={moves}
        onSend={onSend}
        onMove={onMove}
      />
    </span>
  );
}

/** Where the open message can go from its folder. */
function ReaderMoves({
  lng,
  busy,
  moves,
  onSend,
  onMove,
  onForever,
}: Pick<MessageReaderProps, 'lng' | 'busy' | 'moves' | 'onSend' | 'onMove' | 'onForever'>) {
  // Below `sm` a phone has no room for them all: `BridgeMenu` holds the two least used.
  const { t } = useTranslation(lng);
  // A guard, not the attribute: `aria-disabled` keeps the focus where it is.
  const guarded = (act: () => void) => () => {
    if (busy === null) act();
  };
  return (
    <>
      {sendButtons(moves).map(({ act, key, icon: Icon }) => (
        <Button
          key={act}
          variant="ghost"
          size="icon"
          isLoading={busy === act}
          aria-disabled={(busy !== null && busy !== act) || undefined}
          onClick={guarded(() => onSend(act))}
          aria-label={t(key)}
          className={act === 'spam' ? 'hidden sm:inline-flex' : undefined}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </Button>
      ))}
      {moves.move && (
        <Button
          variant="ghost"
          size="icon"
          aria-disabled={busy !== null || undefined}
          onClick={guarded(onMove)}
          aria-label={t('workbench.mail.move_to')}
          className="hidden sm:inline-flex"
        >
          <FolderInput className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
      {!moves.restore && (
        <Button
          variant="ghost"
          size="icon"
          isLoading={busy === 'trash'}
          aria-disabled={(busy !== null && busy !== 'trash') || undefined}
          onClick={guarded(() => onSend('trash'))}
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
          onClick={guarded(onForever)}
          className="text-destructive hover:text-destructive"
          aria-label={t('workbench.mail.delete_forever')}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
    </>
  );
}

/** The one-click ways out of the folder, as the toolbar draws them. */
function sendButtons(moves: MailMoves): { act: MailSendAct; key: string; icon: LucideIcon }[] {
  const all: { act: MailSendAct; key: string; icon: LucideIcon; on: boolean }[] = [
    { act: 'archive', key: 'workbench.mail.archive', icon: Archive, on: moves.archive },
    { act: 'restore', key: 'workbench.mail.restore', icon: ArchiveRestore, on: moves.restore },
    { act: 'not_spam', key: 'workbench.mail.not_spam', icon: Inbox, on: moves.notSpam },
    { act: 'spam', key: 'workbench.mail.report_spam', icon: OctagonAlert, on: moves.spam },
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
}: MessageReaderProps & { message: MailMessage }) {
  const { t } = useTranslation(lng);
  const sender = message.sender;
  const chips = (labels ?? []).filter(label => message.label_ids.includes(label.id));
  const when = receivedFull(message.received_at, zone, lng);
  return (
    <>
      <div className="@container min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
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
        <MessageBody
          lng={lng}
          text={message.body}
          original={original}
          inline={inline}
          originalFailed={originalFailed}
        />
        <AttachmentList
          lng={lng}
          messageId={message.id}
          attachments={message.attachments}
          maxBytes={downloadMax}
          drive={drive}
        />
      </div>
      <nav
        aria-label={t('workbench.mail.answer_bar')}
        className="grid grid-cols-3 border-t bg-card 2xl:hidden"
      >
        <AnswerButton label={t('workbench.mail.reply')} onClick={() => onReply(false)}>
          <Reply className="h-5 w-5 text-primary" aria-hidden="true" />
        </AnswerButton>
        <AnswerButton label={t('workbench.mail.reply_all')} onClick={() => onReply(true)}>
          <ReplyAll className="h-5 w-5 text-primary" aria-hidden="true" />
        </AnswerButton>
        <AnswerButton label={t('workbench.mail.forward')} onClick={onForward}>
          <Forward className="h-5 w-5 text-primary" aria-hidden="true" />
        </AnswerButton>
      </nav>
    </>
  );
}

interface MessageBodyProps {
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
function MessageBody({ lng, text, original, originalFailed, inline }: MessageBodyProps) {
  const { t } = useTranslation(lng);
  const [asText, setAsText] = useState(false);
  // Above the frame, so a look at the text does not take back what the reader asked for.
  const [images, setImages] = useState(false);
  const linksInText = useLinksInText();
  const html = original?.html ?? null;
  const swap = (label: string, next: boolean) => (
    <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setAsText(next)}>
      {label}
    </Button>
  );
  if (html !== null && !asText) {
    return (
      <div className="space-y-2">
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {linksInText && <span>{t('workbench.mail.links_in_text')}</span>}
          {swap(t('workbench.mail.show_text'), true)}
        </p>
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
    <div className="space-y-2">
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">
        <LinkedText text={text} />
      </div>
      {html !== null && swap(t('workbench.mail.show_original'), false)}
      {originalFailed && (
        <p className="text-xs text-muted-foreground">{t('workbench.mail.html_failed')}</p>
      )}
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
