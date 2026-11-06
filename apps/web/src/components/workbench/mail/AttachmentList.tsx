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
 */
import { Download, Eye, FileText, HardDriveUpload } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { ShownReading } from '@/components/workbench/ShownDocument';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useShownDocument } from '@/hooks/useShownDocument';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import apiClient from '@/lib/api-client';
import { cn, generateUUID } from '@/lib/utils';
import { workbenchRefusal } from '@/lib/workbench/errors';
import { attachmentUrl, fileSize } from '@/lib/workbench/mail';
import type { MailAttachment } from '@/lib/workbench/types';

import { FolderPicker } from '../files/FolderPicker';

export interface AttachmentListProps {
  lng: Language;
  messageId: string;
  attachments: readonly MailAttachment[];
  /** The published download ceiling, in bytes. */
  maxBytes: number;
  /** The drive a file can be kept on, when one is ready. */
  drive?: { provider: string | null };
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
        <DialogHeader>
          <DialogTitle className="truncate">{name}</DialogTitle>
          <DialogDescription className="sr-only">
            {t('workbench.mail.preview', { name })}
          </DialogDescription>
        </DialogHeader>
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

export function AttachmentList({
  lng,
  messageId,
  attachments,
  maxBytes,
  drive,
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
      <ul className="grid gap-2 @lg:grid-cols-2">
        {attachments.map((attachment, index) => {
          const size = attachment.size === null ? null : fileSize(attachment.size, lng);
          const tooLarge = attachment.size !== null && attachment.size > maxBytes;
          const name = attachment.filename || t('workbench.mail.unnamed_attachment');
          const offered = attachment.previewable === true && !tooLarge;
          const saving = size
            ? t('workbench.mail.download_sized', { name, size })
            : t('workbench.mail.download', { name });
          const body = (
            <>
              <FileText className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-sm font-medium">{name}</span>
                <span className="text-xs text-muted-foreground">
                  {tooLarge
                    ? t('workbench.mail.attachment_too_large', { max: fileSize(maxBytes, lng) })
                    : size}
                </span>
              </span>
            </>
          );
          return (
            <li key={`${attachment.id ?? 'none'}-${index}`} className="flex items-center gap-1">
              {tooLarge ? (
                <div className="flex min-h-[3.25rem] min-w-0 flex-1 items-center gap-2.5 rounded-lg border bg-card px-3 py-2 opacity-80">
                  {body}
                </div>
              ) : offered ? (
                <button
                  type="button"
                  aria-label={t('workbench.mail.preview', { name })}
                  onClick={() => setReading({ attachment, name })}
                  className={cn(CARD, 'text-left')}
                >
                  {body}
                  <Eye className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </button>
              ) : (
                <a
                  href={attachmentUrl(messageId, attachment)}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={saving}
                  className={CARD}
                >
                  {body}
                  <Download className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </a>
              )}
              {offered && (
                <Button asChild variant="ghost" size="icon" className="shrink-0">
                  <a
                    href={attachmentUrl(messageId, attachment)}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={saving}
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                  </a>
                </Button>
              )}
              {drive && !tooLarge && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0"
                  aria-label={t('workbench.mail.keep_on_drive', { name })}
                  onClick={() => setKeeping(attachment)}
                >
                  <HardDriveUpload className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
            </li>
          );
        })}
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
