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

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { getApiErrorDetail } from '@/lib/api-error';
import { ApiError } from '@/lib/api-client';
import { useBookmarkState } from '@/lib/bookmark-state-context';
import { logger } from '@/lib/logger';

/**
 * The refusals whose `detail` the API translated (the cap, the operator's
 * switch). Any other failure shows this component's own sentence: a 404's
 * detail is an English fallback nobody should read in the chat.
 */
const TRANSLATED_REFUSALS: ReadonlySet<number> = new Set([403, 409]);

/**
 * The sentence to show for a failed toggle.
 *
 * @param error - What the toggle rejected with.
 * @param fallback - This component's own translated sentence.
 * @returns The server's translated sentence when it carries one, else the fallback.
 */
export function refusalSentence(error: unknown, fallback: string): string {
  if (error instanceof ApiError && TRANSLATED_REFUSALS.has(error.status)) {
    return getApiErrorDetail(error) ?? fallback;
  }
  return fallback;
}

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
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => void onClick()}
          aria-label={label}
          aria-pressed={kept}
          aria-busy={busy || undefined}
          data-testid="bookmark-toggle"
          className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors"
        >
          {kept ? (
            <BookmarkCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          ) : (
            <Bookmark className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
