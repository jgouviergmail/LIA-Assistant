'use client';

/**
 * ResponseFeedbackButtons — 👍/👎 on ordinary assistant responses (QW-5,
 * ADR-138).
 *
 * In-flow thumb chips rendered inside the bubble's bottom action row next to
 * Copy (UXR Lot 1 — the former top-right overlay covered the first text lines
 * on mobile). The host row is `flex-wrap`, so the 👎 optional one-line "what
 * went wrong" input wraps to its own full-width line. The verdict is persisted
 * server-side (`POST /conversations/me/messages/{id}/feedback`) and hydrated
 * back from `message_metadata.response_feedback` so it survives reloads and
 * devices. The verdict can be changed (sovereignty) — the backend feeds
 * journal counters on the FIRST verdict only. Never triggers a regeneration.
 */

import { useCallback, useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { useApiMutation } from '@/hooks/useApiMutation';
import { RESPONSE_FEEDBACK_COMMENT_MAX_LENGTH } from '@/lib/constants';

export type ResponseFeedbackVerdict = 'thumbs_up' | 'thumbs_down';

export interface ResponseFeedbackButtonsProps {
  /** DB id of the archived assistant row (live: from the done chunk;
   *  history: the row id). The component is not rendered without one. */
  messageDbId: string;
  /** Verdict hydrated from persisted metadata, if any. */
  initialVerdict?: ResponseFeedbackVerdict;
}

interface FeedbackBody {
  verdict: ResponseFeedbackVerdict;
  comment?: string;
}

export function ResponseFeedbackButtons({
  messageDbId,
  initialVerdict,
}: ResponseFeedbackButtonsProps) {
  const { t } = useTranslation();
  const [verdict, setVerdict] = useState<ResponseFeedbackVerdict | undefined>(initialVerdict);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [commentOpen, setCommentOpen] = useState(false);
  const [comment, setComment] = useState('');

  const { mutate } = useApiMutation<FeedbackBody, { message: string }>({
    method: 'POST',
    componentName: 'ResponseFeedbackButtons',
    onError: () => toast.error(t('chat.feedback.error')),
  });

  const submitVerdict = useCallback(
    async (next: ResponseFeedbackVerdict) => {
      if (isSubmitting || next === verdict) return;
      setIsSubmitting(true);
      // Optimistic: reflect the verdict immediately; onError surfaces a toast.
      setVerdict(next);
      setCommentOpen(next === 'thumbs_down');
      try {
        await mutate(`/conversations/me/messages/${messageDbId}/feedback`, { verdict: next });
        if (next === 'thumbs_up') toast.success(t('chat.feedback.saved'));
      } catch {
        // Handled by onError.
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting, verdict, mutate, messageDbId, t]
  );

  const submitComment = useCallback(async () => {
    const trimmed = comment.trim();
    setCommentOpen(false);
    if (!trimmed || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await mutate(`/conversations/me/messages/${messageDbId}/feedback`, {
        verdict: 'thumbs_down',
        comment: trimmed,
      });
      toast.success(t('chat.feedback.comment_thanks'));
      setComment('');
    } catch {
      // Handled by onError.
    } finally {
      setIsSubmitting(false);
    }
  }, [comment, isSubmitting, mutate, messageDbId, t]);

  const chipClass = (active: boolean, activeClass: string) =>
    `p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors ${
      active ? activeClass : 'text-muted-foreground'
    }`;

  return (
    <>
      {/* Thumb chips — in-flow siblings of the Copy chip inside the bubble's
          action row (the row owns spacing and the top separator). */}
      <button
        type="button"
        onClick={() => submitVerdict('thumbs_up')}
        disabled={isSubmitting}
        aria-label={t('chat.feedback.up')}
        aria-pressed={verdict === 'thumbs_up'}
        className={chipClass(verdict === 'thumbs_up', 'text-green-600 dark:text-green-400')}
      >
        <ThumbsUp className="h-3.5 w-3.5" aria-hidden />
      </button>
      <button
        type="button"
        onClick={() => submitVerdict('thumbs_down')}
        disabled={isSubmitting}
        aria-label={t('chat.feedback.down')}
        aria-pressed={verdict === 'thumbs_down'}
        className={chipClass(verdict === 'thumbs_down', 'text-orange-600 dark:text-orange-400')}
      >
        <ThumbsDown className="h-3.5 w-3.5" aria-hidden />
      </button>

      {/* 👎 optional one-line correction — `w-full` wraps it to its own line
          under the flex-wrap action row. */}
      {commentOpen && (
        <div className="w-full flex items-center gap-2 mt-1">
          <input
            type="text"
            value={comment}
            onChange={e => setComment(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') void submitComment();
              if (e.key === 'Escape') setCommentOpen(false);
            }}
            maxLength={RESPONSE_FEEDBACK_COMMENT_MAX_LENGTH}
            placeholder={t('chat.feedback.comment_placeholder')}
            aria-label={t('chat.feedback.comment_placeholder')}
            className="flex-1 h-8 px-2 text-xs rounded-md bg-background border border-border focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => void submitComment()}
            disabled={isSubmitting}
            className="text-xs font-semibold text-primary hover:text-primary/80 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {t('chat.feedback.comment_send')}
          </button>
        </div>
      )}
    </>
  );
}
