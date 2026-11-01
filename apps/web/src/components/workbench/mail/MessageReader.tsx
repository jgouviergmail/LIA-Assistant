'use client';

/**
 * MessageReader — one message, read (ADR-369, mock-ups « Main » and
 * « Mobile — message »).
 *
 * The subject, who sent it to whom, when (in the account's zone), the
 * person's labels, the message — its original layout in a sandboxed frame on
 * its own paper when it has one (D3; its text a click away, since links do not
 * open in the frame), else the provider's clean text in the theme's colours —
 * and the files. The
 * toolbar answers, forwards, marks unread or read, labels (Gmail) and trashes;
 * on a phone the answers sit in a bar at the bottom, where the thumb is.
 * Below `xl` the reader replaces the list, so its first control leads back to
 * the folder, and it takes the focus when it opens below `lg`.
 */
import { ChevronLeft, Forward, Mail, MailOpen, Reply, ReplyAll, Trash2, X } from 'lucide-react';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { addressLabel, initials } from '@/lib/workbench/mail';
import type { MailAddress, MailFolder, MailHtml, MailMessage } from '@/lib/workbench/types';

import { AttachmentList } from './AttachmentList';
import { LabelMenu } from './LabelMenu';

// The original-layout reader parses an inert document with browser DOM APIs.
const MailHtmlFrame = dynamic(
  () => import('./MailHtmlFrame').then(module => module.MailHtmlFrame),
  {
    ssr: false,
  }
);

/** Which act of the reader is on its way, if any. */
export type ReaderAct = 'read' | 'trash' | 'labels';

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
  busy: ReaderAct | null;
  focusOnOpen: boolean;
  onClose: () => void;
  onRetry: () => void;
  onReply: (all: boolean) => void;
  onForward: () => void;
  onToggleRead: (read: boolean) => void;
  onTrash: () => void;
  onLabels: (add: string[], remove: string[]) => void;
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
  const { lng, message, loading, error, backLabel, focusOnOpen, onClose, onRetry } = props;
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
      {content}
    </article>
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
  onTrash,
  onLabels,
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
      <Button
        variant="ghost"
        size="icon"
        isLoading={busy === 'trash'}
        aria-disabled={(busy !== null && busy !== 'trash') || undefined}
        onClick={guarded(onTrash)}
        className="text-destructive hover:text-destructive"
        aria-label={t('workbench.mail.trash')}
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
      </Button>
    </span>
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
  onReply,
  onForward,
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
          originalFailed={originalFailed}
        />
        <AttachmentList
          lng={lng}
          messageId={message.id}
          attachments={message.attachments}
          maxBytes={downloadMax}
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
}

/** The original layout when the message has one, else (or on demand) its text. */
function MessageBody({ lng, text, original, originalFailed }: MessageBodyProps) {
  const { t } = useTranslation(lng);
  const [asText, setAsText] = useState(false);
  const html = original?.html ?? null;
  const swap = (label: string, next: boolean) => (
    <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setAsText(next)}>
      {label}
    </Button>
  );
  if (html !== null && !asText) {
    return (
      <div className="space-y-2">
        {/* Above the frame: why its images are missing, and the way to the links, in sight. */}
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <span>{t('workbench.mail.html_notice')}</span>
          {swap(t('workbench.mail.show_text'), true)}
        </p>
        {original?.truncated && (
          <p className="text-xs text-muted-foreground">{t('workbench.mail.html_truncated')}</p>
        )}
        <MailHtmlFrame lng={lng} html={html} />
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground">
        {text}
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
