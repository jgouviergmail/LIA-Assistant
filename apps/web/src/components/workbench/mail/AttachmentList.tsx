'use client';

/**
 * AttachmentList — a message's files (ADR-369, mock-up « Mobile — message »).
 *
 * A file the API can read opens from its card, in a window of the page, as a drive's
 * file is: an image, a PDF, a Word file, a table, a text, whichever device reads it.
 * Its download stands beside it; any other file's card is its download. A download
 * goes through the API's own door (`/workbench/mail/attachment`: served as a file,
 * never rendered, sandboxed, kept by no cache), in a new tab as the app's other
 * downloads are, so a refusal never replaces the screen. A file the provider says is
 * larger than the published ceiling (`limits.download_max_bytes`, ADR-184) is listed
 * and said too large here rather than offered for a download that would be refused.
 * Where a drive is ready, a file that can be read can be kept in one of its folders.
 * What LIA can do on a file joins that act under one icon of the same width: a phone's
 * row gains no control (ADR-372).
 */
import { Download, Eye, FileText, HardDriveUpload } from '@/lib/icons';
import { useState } from 'react';
import { toast } from 'sonner';

import { ShownReading } from '@/components/workbench/ShownDocument';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useShownDocument } from '@/hooks/useShownDocument';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { cn, generateUUID } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { attachmentUrl, fileSize } from '@/lib/workbench/mail';
import type { MailAttachment } from '@/lib/workbench/types';

import { AssistStars } from '@/components/selection-assist/AssistStars';
import { BarAct, type DetailDeed } from '../DetailBar';
import { FolderPicker } from '../files/FolderPicker';
import { ToolDialogHeader } from '../ToolForm';

export interface AttachmentListProps {
  lng: Language;
  messageId: string;
  attachments: readonly MailAttachment[];
  /** The published download ceiling, in bytes. */
  maxBytes: number;
  /** The drive a file can be kept on, when one is ready. */
  drive?: { provider: string | null };
  /** What LIA can do on a file. */
  lines?: (attachment: MailAttachment, name: string) => readonly DetailDeed[];
}

const READING_PATH = '/workbench/mail/attachment/preview';
/** A file of the message: the same card whether it opens or saves. */
const CARD =
  'flex min-h-[3.25rem] min-w-0 flex-1 items-center gap-2.5 rounded-lg border bg-card px-3 py-2 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** What the API reads of a file of the message, in a window of the page. */
function AttachmentReading({
  lng,
  messageId,
  attachment,
  name,
  onClose,
}: {
  lng: Language;
  messageId: string;
  attachment: MailAttachment;
  name: string;
  onClose: () => void;
}) {
  const { t } = useTranslation(lng);
  const read = useShownDocument(READING_PATH, {
    message_id: messageId,
    attachment_id: attachment.id ?? undefined,
    filename: attachment.filename,
  });
  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-5xl">
        <ToolDialogHeader>
          <DialogTitle className="truncate">{name}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('workbench.mail.preview', { name })}
          </DialogDescription>
        </ToolDialogHeader>
        <ShownReading lng={lng} read={read} name={name} large />
      </DialogContent>
    </Dialog>
  );
}

/** Where a file of the message goes on the drive, once per submission. */
function KeepOnDrive({
  lng,
  provider,
  messageId,
  attachment,
  onClose,
}: {
  lng: Language;
  provider: string | null;
  messageId: string;
  attachment: MailAttachment;
  onClose: () => void;
}) {
  const { t } = useTranslation(lng);
  const [key] = useState(() => generateUUID());
  const keep = async (folderId: string | null) => {
    try {
      await apiClient.post('/workbench/files/from-mail', {
        message_id: messageId,
        attachment_id: attachment.id,
        filename: attachment.filename,
        folder_id: folderId,
        idempotency_key: key,
      });
      toast.success(t('workbench.mail.kept_on_drive'));
      return true;
    } catch (error: unknown) {
      const refusal = workbenchRefusal(error);
      toast.error(refusal ? t(refusal.key, refusal.values) : t('workbench.mail.keep_failed'));
      return false;
    }
  };
  return (
    <FolderPicker
      lng={lng}
      provider={provider}
      title={t('workbench.mail.keep_title', { name: attachment.filename })}
      submitLabel={t('workbench.mail.keep_here')}
      trail={[]}
      leaving={[]}
      onClose={onClose}
      onPick={folderId => keep(folderId)}
    />
  );
}

/** What a row says of its file: its name, then its size or why it stays where it is. */
function FileWords({
  name,
  note,
}: {
  name: string;
  /** Its size, or why it cannot leave. */
  note: string | null;
}) {
  return (
    <>
      <FileText className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium">{name}</span>
        <span className="text-xs text-muted-foreground">{note}</span>
      </span>
    </>
  );
}

/** The last icon of a row: what LIA offers with the drive, or the drive alone, in the same room. */
function RowAct({
  lng,
  name,
  lines,
  onDrive,
}: {
  lng: Language;
  name: string;
  lines: readonly DetailDeed[];
  /** Keeps it on the drive; left out where there is none or it could not leave. */
  onDrive?: () => void;
}) {
  const { t } = useTranslation(lng);
  const keep = t('workbench.mail.keep_on_drive', { name });
  if (lines.length > 0) {
    const drive = onDrive ? [{ label: keep, icon: HardDriveUpload, onSelect: onDrive }] : [];
    return (
      <BarAct
        act={{
          label: t('workbench.assist.mail.attachment_menu', { name }),
          icon: AssistStars,
          choices: [...lines, ...drive],
        }}
      />
    );
  }
  if (!onDrive) return null;
  return (
    <Button variant="ghost" size="icon" className="shrink-0" aria-label={keep} onClick={onDrive}>
      <HardDriveUpload className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}

/** One file of the message: a card that opens or saves it, and what else it offers. */
function AttachmentRow({
  lng,
  messageId,
  attachment,
  maxBytes,
  drive,
  lines,
  onKeep,
  onRead,
}: {
  lng: Language;
  messageId: string;
  attachment: MailAttachment;
  maxBytes: number;
  drive: boolean;
  lines: AttachmentListProps['lines'];
  onKeep: () => void;
  onRead: (name: string) => void;
}) {
  const { t } = useTranslation(lng);
  const size = attachment.size === null ? null : fileSize(attachment.size, lng);
  const tooLarge = attachment.size !== null && attachment.size > maxBytes;
  const name = attachment.filename || t('workbench.mail.unnamed_attachment');
  const offered = attachment.previewable === true && !tooLarge;
  const saving = size
    ? t('workbench.mail.download_sized', { name, size })
    : t('workbench.mail.download', { name });
  const href = attachmentUrl(messageId, attachment);
  if (tooLarge) {
    const note = t('workbench.mail.attachment_too_large', { max: fileSize(maxBytes, lng) });
    return (
      <li className="flex items-center gap-1">
        <div className="flex min-h-[3.25rem] min-w-0 flex-1 items-center gap-2.5 rounded-lg border bg-card px-3 py-2 opacity-80">
          <FileWords name={name} note={note} />
        </div>
      </li>
    );
  }
  return (
    <li className="flex items-center gap-1">
      {offered ? (
        <button
          type="button"
          aria-label={t('workbench.mail.preview', { name })}
          onClick={() => onRead(name)}
          className={cn(CARD, 'text-left')}
        >
          <FileWords name={name} note={size} />
          <Eye className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      ) : (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={saving}
          className={CARD}
        >
          <FileWords name={name} note={size} />
          <Download className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </a>
      )}
      {offered && (
        <Button asChild variant="ghost" size="icon" className="shrink-0">
          <a href={href} target="_blank" rel="noopener noreferrer" aria-label={saving}>
            <Download className="h-4 w-4" aria-hidden="true" />
          </a>
        </Button>
      )}
      <RowAct
        lng={lng}
        name={name}
        lines={lines?.(attachment, name) ?? []}
        onDrive={drive ? onKeep : undefined}
      />
    </li>
  );
}

export function AttachmentList({
  lng,
  messageId,
  attachments,
  maxBytes,
  drive,
  lines,
}: AttachmentListProps) {
  const { t } = useTranslation(lng);
  const [keeping, setKeeping] = useState<MailAttachment | null>(null);
  const [reading, setReading] = useState<{ attachment: MailAttachment; name: string } | null>(null);
  if (attachments.length === 0) return null;
  const title = t('workbench.mail.attachments', { count: attachments.length });
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <ul className="grid grid-cols-1 gap-2 @lg:grid-cols-2">
        {attachments.map((attachment, index) => (
          <AttachmentRow
            key={`${attachment.id ?? 'none'}-${index}`}
            lng={lng}
            messageId={messageId}
            attachment={attachment}
            maxBytes={maxBytes}
            drive={Boolean(drive)}
            lines={lines}
            onKeep={() => setKeeping(attachment)}
            onRead={name => setReading({ attachment, name })}
          />
        ))}
      </ul>
      {keeping && drive && (
        <KeepOnDrive
          lng={lng}
          provider={drive.provider}
          messageId={messageId}
          attachment={keeping}
          onClose={() => setKeeping(null)}
        />
      )}
      {reading && (
        <AttachmentReading
          lng={lng}
          messageId={messageId}
          attachment={reading.attachment}
          name={reading.name}
          onClose={() => setReading(null)}
        />
      )}
    </section>
  );
}
