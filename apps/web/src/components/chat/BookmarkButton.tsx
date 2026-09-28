'use client';

/**
 * The bookmark toggle of an assistant bubble (ADR-282).
 *
 * Same chip family as « copy », right beside it. Filled when the answer is
 * kept, empty otherwise; one click keeps, the next lets go. Drawn only for a
 * bubble that carries its archived id (the same gate as the feedback chips)
 * inside a chat whose instance offers bookmarks — outside that, nothing.
 *
 * A refusal says why: the cap and the operator's switch both come back as
 * sentences the API translated, and a sentence is what the toast shows.
 */

import { Bookmark, BookmarkCheck } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { refusalSentence } from '@/lib/api-error';
import { useBookmarkState } from '@/lib/bookmark-state-context';
import { logger } from '@/lib/logger';

import { ActionChipButton } from './ActionChipButton';

export interface BookmarkButtonProps {
  /** The archived message id the bubble carries (`metadata.message_db_id`). */
  messageDbId: string;
}

export function BookmarkButton({ messageDbId }: BookmarkButtonProps) {
  const { t } = useTranslation();
  const { enabled, bookmarkIdOf, toggle } = useBookmarkState();
  const [busy, setBusy] = useState(false);
  const kept = bookmarkIdOf(messageDbId) !== undefined;

  const onClick = useCallback(async () => {
    // A guard in the handler, never `disabled` on the control that holds the
    // focus: the browser would blur it and drop it from the tab order.
    if (busy) return;
    setBusy(true);
    try {
      const state = await toggle(messageDbId);
      toast.success(
        state === 'kept' ? t('chat.message.bookmark_kept') : t('chat.message.bookmark_removed')
      );
    } catch (error) {
      logger.error('bookmark_toggle_failed', error as Error, {
        component: 'BookmarkButton',
        messageDbId,
      });
      toast.error(refusalSentence(error, t('chat.message.bookmark_error')));
    } finally {
      setBusy(false);
    }
  }, [busy, messageDbId, t, toggle]);

  if (!enabled) return null;

  const label = kept ? t('chat.message.bookmark_remove') : t('chat.message.bookmark');
  return (
    <ActionChipButton
      label={label}
      onClick={() => void onClick()}
      aria-pressed={kept}
      aria-busy={busy || undefined}
      data-testid="bookmark-toggle"
    >
      {kept ? (
        <BookmarkCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
      ) : (
        <Bookmark className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
      )}
    </ActionChipButton>
  );
}
