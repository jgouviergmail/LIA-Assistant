'use client';

import { useRef, useState } from 'react';
import { Clock3, MessageSquareOff, ThumbsUp, CircleHelp, Reply } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources } from '@/lib/application-resources';
import { ActionChipButton } from '@/components/chat/ActionChipButton';
import { z } from '@/lib/zod';
import {
  discussionFeedbackSchema,
  discussionOpeningSchema,
  type DiscussionFeedback,
} from '@/types/proactive-discussions';

const choices = [
  { key: 'useful', icon: ThumbsUp },
  { key: 'not_now', icon: Clock3 },
  { key: 'avoid_topic', icon: MessageSquareOff },
  { key: 'incorrect', icon: CircleHelp },
] as const;

export function DiscussionActions({
  metadata,
  content,
  onPrefillComposer,
}: {
  metadata: Record<string, unknown> | undefined;
  content?: string;
  onPrefillComposer?: (text: string) => void;
}) {
  const { user } = useAuth();
  const identity = z.string().uuid().safeParse(metadata?.discussion_id);
  if (metadata?.type !== 'proactive_discussion' || !identity.success) return null;
  const feedback = discussionFeedbackSchema
    .nullable()
    .safeParse(metadata.discussion_feedback ?? null);
  // The pause this opening's "not now" promises, written when it was published.
  const pause = z.number().int().positive().safeParse(metadata.discussion_pause_hours);
  return (
    <DiscussionFeedbackActions
      key={`${user?.id ?? 'signed-out'}:${identity.data}:${feedback.success ? (feedback.data ?? 'none') : 'none'}`}
      openingId={identity.data}
      recorded={feedback.success ? feedback.data : null}
      pauseHours={pause.success ? pause.data : null}
      content={content}
      onPrefillComposer={onPrefillComposer}
    />
  );
}

/**
 * The answers a discussion LIA opened offers: the bubble row's own chips, a shade
 * deeper so they read as this discussion's, never as a new kind of control.
 */
function DiscussionFeedbackActions({
  openingId,
  recorded,
  pauseHours,
  content,
  onPrefillComposer,
}: {
  openingId: string;
  recorded: DiscussionFeedback | null;
  pauseHours: number | null;
  content?: string;
  onPrefillComposer?: (text: string) => void;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [receipt, setReceipt] = useState<DiscussionFeedback | null>(recorded);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const locked = useRef(false);
  const { mutate } = useApiMutation<object, unknown>({
    method: 'POST',
    componentName: 'DiscussionActions',
    retainResponse: false,
  });
  async function submit(feedback: DiscussionFeedback) {
    // The guard, not the attribute, prevents a second answer: a control the click
    // just landed on is never disabled (it would drop the keyboard user's focus).
    if (locked.current || receipt !== null || !isCurrent()) return;
    locked.current = true;
    setBusy(true);
    setFailed(false);
    try {
      const result = discussionOpeningSchema.parse(
        await mutate(`/proactive-discussions/openings/${openingId}/feedback`, {
          feedback,
          expected_feedback: receipt,
        })
      );
      if (result.id !== openingId || result.feedback !== feedback)
        throw new Error('Invalid discussion receipt');
      if (isCurrent()) {
        setReceipt(result.feedback);
        if (user?.id) publishApplicationResources(user.id, new Set(['proactive_discussions']));
      }
    } catch {
      if (isCurrent()) setFailed(true);
    } finally {
      locked.current = false;
      if (isCurrent()) setBusy(false);
    }
  }
  const answered = busy || receipt !== null;
  return (
    // A line of its own, under the bubble's actions and aligned on them (owner
    // request 2026-10-21): in the row's flex-wrap, `basis-full` starts a line.
    <span className="flex w-full basis-full flex-wrap items-center gap-1" aria-busy={busy}>
      {content && onPrefillComposer && (
        <ActionChipButton
          tone="deeper"
          label={t('discussions.reply')}
          onClick={() => onPrefillComposer(t('discussions.reply_prefill', { text: content }))}
        >
          <Reply className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        </ActionChipButton>
      )}
      {choices.map(({ key, icon: Icon }) => {
        const label =
          key !== 'not_now'
            ? t(`discussions.feedback.${key}`)
            : pauseHours === null
              ? t('discussions.feedback.not_now_plain')
              : t('discussions.feedback.not_now', { hours: pauseHours });
        const chosen = receipt === key;
        return (
          <ActionChipButton
            key={key}
            tone="deeper"
            label={label}
            aria-pressed={chosen}
            aria-disabled={answered}
            className={answered ? 'cursor-default' : undefined}
            onClick={() => void submit(key)}
          >
            <Icon
              className={`h-3.5 w-3.5 ${chosen ? 'text-primary' : 'text-muted-foreground'}`}
              aria-hidden="true"
            />
          </ActionChipButton>
        );
      })}
      {failed && (
        <span role="alert" className="text-xs text-destructive">
          {t('discussions.feedback.error')}
        </span>
      )}
      {receipt && (
        <span role="status" className="sr-only">
          {t('discussions.feedback.saved')}
        </span>
      )}
    </span>
  );
}
