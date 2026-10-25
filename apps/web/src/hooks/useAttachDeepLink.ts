'use client';

/**
 * The chat's `?attach=<kind>:<id>` — something the person holds joins the composer.
 *
 * A « Use in the discussion » button on the bookmarks or the gallery page is a
 * plain link (owner request 2026-10-24): the composer asks the API for a COPY
 * and adds it to the strip, where the person reviews it before sending. Like
 * `?draft=`, the param leaves the address on arrival, so a reload attaches
 * nothing; a link replayed from the history can only attach another copy —
 * never send anything. What the API refuses (not the person's, past its
 * deadline, gone) is said, never silently dropped.
 */

import { useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import type { AddServerAttachmentOutcome, ServerAttachmentMeta } from '@/hooks/useFileUpload';
import { ApiError } from '@/lib/api-client';
import { parseAttachSource } from '@/lib/attach-source-link';
import { attachmentMeta, copyAttachSource } from '@/lib/attach-sources';
import { dropSearchParams } from '@/lib/chat-deep-link';

/**
 * Consume `?attach=` once: copy the named source and hand it to the strip.
 *
 * @param enabled - Whether attachments are on (the copy is an upload).
 * @param onAttached - The strip's door.
 */
export function useAttachDeepLink(
  enabled: boolean,
  onAttached: (meta: ServerAttachmentMeta) => AddServerAttachmentOutcome
): void {
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const raw = searchParams?.get('attach') ?? null;
  // Keyed on the VALUE: a dev double effect or a re-render attaches it once.
  const handled = useRef(new Set<string>());

  useEffect(() => {
    if (!raw) return;
    dropSearchParams(['attach']);
    const source = parseAttachSource(raw);
    if (!enabled || !source || handled.current.has(raw)) return;
    handled.current.add(raw);
    copyAttachSource(source)
      .then(created => {
        const outcome = onAttached(attachmentMeta(created));
        if ('error' in outcome)
          toast.error(
            outcome.error === 'max_attachments'
              ? t('chat.attachments.max_attachments', { max: outcome.max })
              : t('chat.attach_picker.already_attached')
          );
      })
      .catch((error: unknown) => {
        const gone = error instanceof ApiError && error.status === 404;
        toast.error(t(gone ? 'chat.attach_link.gone' : 'chat.attach_link.failed'));
      });
  }, [raw, enabled, onAttached, t]);
}
