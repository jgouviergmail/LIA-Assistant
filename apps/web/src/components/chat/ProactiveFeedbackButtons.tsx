'use client';

/**
 * ProactiveFeedbackButtons — 👍/👎/🚫 for a proactive notification.
 *
 * Rendered as in-flow chips of the bubble's action row, right after the copy
 * chip — the same place, and the same shape, as the thumbs on an ordinary
 * assistant answer (`ResponseFeedbackButtons`). They used to sit INSIDE the
 * bubble under the text, introduced by a full sentence ("Was this useful?"),
 * which made the same gesture look like two different features depending on
 * which kind of message you were reading. The row already says what it is.
 *
 * The two sets never appear together: `responseFeedbackProps` returns null for
 * proactive bubbles.
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
 * Once a verdict is given the chips STAY, with the chosen one pressed and all
 * of them disabled — the same read as a voted assistant answer. Disabled and
 * not merely unchanged: a proactive verdict is final server-side (a "block"
 * really blocks the subject), so an enabled chip would promise a reversibility
 * the product does not offer. The state survives reloads and devices because
 * the backend persists it as `feedback_value`
 * (`mark_proactive_feedback_submitted`).
 */

import { useCallback, useState } from 'react';
import { Ban, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useApiMutation } from '@/hooks/useApiMutation';

/* A failed submission never surfaces an error toast (owner arbitration
 * 2026-07-30): the vote is optimistic and final in the UI, and older
 * notifications may legitimately have no matching backend row anymore (404) —
 * shouting at the user about a preference ping is worse than dropping it.
 * `useApiMutation` still records every failure via its structured client
 * logger, so the signal is kept, just not shown. */

export type ProactiveFeedbackKind = 'interest' | 'heartbeat';
export type ProactiveFeedbackVerdict = 'thumbs_up' | 'thumbs_down' | 'block';

export interface ProactiveFeedbackButtonsProps {
  /** Which backend contract to speak. */
  kind: ProactiveFeedbackKind;
  /** Interest id, or heartbeat notification id — the metadata `target_id`. */
  targetId: string;
  /** Notification run id, when the card carries one (interest only). */
  runId?: string;
  /** Called once, optimistically, with the verdict the user chose. */
  onFeedbackSubmitted: (verdict: ProactiveFeedbackVerdict) => void;
  /** Verdict already recorded — chips then show it pressed and disabled. */
  submittedVerdict?: ProactiveFeedbackVerdict;
}

interface KindContract {
  /** Verdicts this kind accepts, in display order. */
  verdicts: readonly ProactiveFeedbackVerdict[];
  path: (targetId: string) => string;
  method: 'POST' | 'PATCH';
  /** i18n namespace holding `like` / `dislike` / `block` / `error` + toasts. */
  ns: string;
}

const CONTRACTS: Record<ProactiveFeedbackKind, KindContract> = {
  interest: {
    verdicts: ['thumbs_up', 'thumbs_down', 'block'],
    path: id => `/interests/${id}/feedback`,
    method: 'POST',
    ns: 'interests.feedback',
  },
  heartbeat: {
    verdicts: ['thumbs_up', 'thumbs_down'],
    path: id => `/heartbeat/notifications/${id}/feedback`,
    method: 'PATCH',
    ns: 'heartbeat.feedback',
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
    activeClassName: 'text-green-600 dark:text-green-400',
  },
  thumbs_down: {
    Icon: ThumbsDown,
    labelKey: 'dislike',
    toastKey: 'disliked',
    toastKind: 'info',
    className: 'hover:bg-orange-100 hover:text-orange-600 dark:hover:bg-orange-900/30',
    activeClassName: 'text-orange-600 dark:text-orange-400',
  },
  block: {
    Icon: Ban,
    labelKey: 'block',
    toastKey: 'blocked',
    toastKind: 'info',
    className: 'hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30',
    activeClassName: 'text-red-600 dark:text-red-400',
  },
} as const;

export function ProactiveFeedbackButtons({
  kind,
  targetId,
  runId,
  onFeedbackSubmitted,
  submittedVerdict,
}: ProactiveFeedbackButtonsProps) {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const contract = CONTRACTS[kind];

  const { mutate } = useApiMutation<{ feedback: ProactiveFeedbackVerdict; run_id?: string }, void>({
    method: contract.method,
    componentName: 'ProactiveFeedbackButtons',
  });

  const handleFeedback = useCallback(
    async (verdict: ProactiveFeedbackVerdict) => {
      if (isSubmitting || submittedVerdict) return;
      setIsSubmitting(true);

      // Optimistic: the parent locks the row on this verdict immediately; a
      // failed request is logged but never toasted (see the note above);
      // `isSubmitting` only guards the double click before that lock lands.
      onFeedbackSubmitted(verdict);
      const { toastKey, toastKind } = VERDICT_UI[verdict];
      toast[toastKind](t(`${contract.ns}.${toastKey}`));

      try {
        await mutate(contract.path(targetId), {
          feedback: verdict,
          ...(kind === 'interest' && runId ? { run_id: runId } : {}),
        });
      } catch {
        // Already logged by useApiMutation; deliberately not surfaced.
      }
    },
    [
      isSubmitting,
      submittedVerdict,
      onFeedbackSubmitted,
      t,
      contract,
      mutate,
      targetId,
      kind,
      runId,
    ]
  );

  // Fragment, not a container: the chips are in-flow siblings of the copy chip,
  // and the action row owns the spacing — exactly like ResponseFeedbackButtons.
  // The tooltips stay: "block" is the one verdict whose icon does not say what
  // it does, and it is irreversible for the user's interests.
  return (
    <>
      {contract.verdicts.map(verdict => {
        const { Icon, labelKey, className, activeClassName } = VERDICT_UI[verdict];
        const label = t(`${contract.ns}.${labelKey}`);
        const decided = submittedVerdict !== undefined;
        const chosen = submittedVerdict === verdict;
        return (
          <Tooltip key={verdict}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleFeedback(verdict)}
                disabled={isSubmitting || decided}
                aria-label={label}
                aria-pressed={decided ? chosen : undefined}
                className={`rounded-md border border-border/30 bg-background/80 p-1.5 transition-colors ${
                  chosen ? activeClassName : 'text-muted-foreground'
                } ${decided ? 'disabled:opacity-100' : `hover:bg-background ${className}`}`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
              </button>
            </TooltipTrigger>
            <TooltipContent>{label}</TooltipContent>
          </Tooltip>
        );
      })}
    </>
  );
}
