'use client';

/**
 * AttachmentList — a message's files (ADR-369, mock-up « Mobile — message »).
 *
 * Each file is a download through the API's own door (`/workbench/mail/attachment`:
 * served as a file, never rendered, sandboxed, kept by no cache), opened in a
 * new tab as the app's other downloads are, so a refusal never replaces the
 * screen. A file the provider says is larger than the published ceiling
 * (`limits.download_max_bytes`, ADR-184) is listed and said too large here
 * rather than offered for a download that would be refused.
 */
import { Download, FileText } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { attachmentUrl, fileSize } from '@/lib/workbench/mail';
import type { MailAttachment } from '@/lib/workbench/types';

export interface AttachmentListProps {
  lng: Language;
  messageId: string;
  attachments: readonly MailAttachment[];
  /** The published download ceiling, in bytes. */
  maxBytes: number;
}

export function AttachmentList({ lng, messageId, attachments, maxBytes }: AttachmentListProps) {
  const { t } = useTranslation(lng);
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
            <li key={`${attachment.id ?? 'none'}-${index}`}>
              {tooLarge ? (
                <div className="flex min-h-[3.25rem] items-center gap-2.5 rounded-lg border bg-card px-3 py-2 opacity-80">
                  {body}
                </div>
              ) : (
                <a
                  href={attachmentUrl(messageId, attachment)}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={
                    size
                      ? t('workbench.mail.download_sized', { name, size })
                      : t('workbench.mail.download', { name })
                  }
                  className="flex min-h-[3.25rem] items-center gap-2.5 rounded-lg border bg-card px-3 py-2 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {body}
                  <Download className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
