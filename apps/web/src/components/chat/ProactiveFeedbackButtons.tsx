'use client';

/**
 * ProactiveFeedbackButtons — 👍/👎/🚫 under a proactive notification bubble.
 *
 * Extracted from `ChatMessage` (render hotspot under a shrink-only complexity
 * ratchet) and generalised to both kinds of proactive push:
 *
 * - `interest`  → `POST /interests/{id}/feedback`, three verdicts. The card's
 *   `run_id` travels with the verdict so the notification audit trail records
 *   it on the exact notification instead of a guessed row.
 * - `heartbeat` → `PATCH /heartbeat/notifications/{id}/feedback`, two verdicts
 *   (the backend contract has no "block"). These buttons did not exist: the
 *   metadata said `feedback_enabled: true` and the endpoint worked, but no
 *   component ever rendered them — 914 production notifications with no way to
 *   answer them (measured 2026-07-27).
 *
 * The verdict is one-way in the UI: the parent unmounts the row on
 * `onFeedbackSubmitted`, and the server hides it across reloads by marking the
 * archived message metadata (`mark_proactive_feedback_submitted`).
 */

import { useCallback, useState } from 'react';
import { Ban, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useApiMutation } from '@/hooks/useApiMutation';

export type ProactiveFeedbackKind = 'interest' | 'heartbeat';
export type ProactiveFeedbackVerdict = 'thumbs_up' | 'thumbs_down' | 'block';

export interface ProactiveFeedbackButtonsProps {
  /** Which backend contract to speak. */
  kind: ProactiveFeedbackKind;
  /** Interest id, or heartbeat notification id — the metadata `target_id`. */
  targetId: string;
  /** Notification run id, when the card carries one (interest only). */
  runId?: string;
  /** Called once, optimistically, as soon as a verdict is chosen. */
  onFeedbackSubmitted: () => void;
}

interface KindContract {
  /** Verdicts this kind accepts, in display order. */
  verdicts: readonly ProactiveFeedbackVerdict[];
  path: (targetId: string) => string;
  method: 'POST' | 'PATCH';
  /** i18n namespace holding `like` / `dislike` / `block` / `error` + toasts. */
  ns: string;
  /** Label introducing the row — kept per kind so a heartbeat card never
   *  borrows a string from the interests namespace. */
  promptKey: string;
}

const CONTRACTS: Record<ProactiveFeedbackKind, KindContract> = {
  interest: {
    verdicts: ['thumbs_up', 'thumbs_down', 'block'],
    path: id => `/interests/${id}/feedback`,
    method: 'POST',
    ns: 'interests.feedback',
    promptKey: 'interests.notification.helpful',
  },
  heartbeat: {
    verdicts: ['thumbs_up', 'thumbs_down'],
    path: id => `/heartbeat/notifications/${id}/feedback`,
    method: 'PATCH',
    ns: 'heartbeat.feedback',
    promptKey: 'heartbeat.feedback.helpful',
  },
};

/** Icon, hover tint and acknowledgement per verdict — shared by both kinds.
 *  Only the positive verdict celebrates: "less of this" is acknowledged
 *  neutrally, never congratulated. */
const VERDICT_UI = {
  thumbs_up: {
    Icon: ThumbsUp,
    labelKey: 'like',
    toastKey: 'liked',
    toastKind: 'success',
    className: 'hover:bg-green-100 hover:text-green-600 dark:hover:bg-green-900/30',
  },
  thumbs_down: {
    Icon: ThumbsDown,
    labelKey: 'dislike',
    toastKey: 'disliked',
    toastKind: 'info',
    className: 'hover:bg-orange-100 hover:text-orange-600 dark:hover:bg-orange-900/30',
  },
  block: {
    Icon: Ban,
    labelKey: 'block',
    toastKey: 'blocked',
    toastKind: 'info',
    className: 'hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30',
  },
} as const;

export function ProactiveFeedbackButtons({
  kind,
  targetId,
  runId,
  onFeedbackSubmitted,
}: ProactiveFeedbackButtonsProps) {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const contract = CONTRACTS[kind];

  const { mutate } = useApiMutation<{ feedback: ProactiveFeedbackVerdict; run_id?: string }, void>({
    method: contract.method,
    componentName: 'ProactiveFeedbackButtons',
    onError: () => toast.error(t(`${contract.ns}.error`)),
  });

  const handleFeedback = useCallback(
    async (verdict: ProactiveFeedbackVerdict) => {
      if (isSubmitting) return;
      setIsSubmitting(true);

      // Optimistic: the parent drops this row immediately, so a failed request
      // surfaces its own error toast but never brings the buttons back;
      // `isSubmitting` only guards the double click before that unmount.
      onFeedbackSubmitted();
      const { toastKey, toastKind } = VERDICT_UI[verdict];
      toast[toastKind](t(`${contract.ns}.${toastKey}`));

      try {
        await mutate(contract.path(targetId), {
          feedback: verdict,
          ...(kind === 'interest' && runId ? { run_id: runId } : {}),
        });
      } catch {
        // Handled by onError.
      }
    },
    [isSubmitting, onFeedbackSubmitted, t, contract, mutate, targetId, kind, runId]
  );

  return (
    <div className="flex items-center gap-1 mt-2">
      <span className="text-xs text-muted-foreground mr-2">
        {t(contract.promptKey)}
      </span>
      {contract.verdicts.map(verdict => {
        const { Icon, labelKey, className } = VERDICT_UI[verdict];
        const label = t(`${contract.ns}.${labelKey}`);
        return (
          <Tooltip key={verdict}>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className={`h-7 w-7 ${className}`}
                onClick={() => handleFeedback(verdict)}
                disabled={isSubmitting}
                aria-label={label}
              >
                <Icon className="h-4 w-4" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
