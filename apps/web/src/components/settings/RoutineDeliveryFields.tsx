'use client';

import { useTranslation } from 'react-i18next';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

interface RoutineDeliveryFieldsProps {
  /** Prefix of the two controls' ids — the form may be mounted more than once. */
  idPrefix: string;
  requiresApproval: boolean;
  notifyOnlyWhenNew: boolean;
  onChange: (delivery: { requires_approval: boolean; notify_only_when_new: boolean }) => void;
  /**
   * « Ask first » is ruled out: a routine started by calls hands no run to the
   * chat, which would never read the calls it serves (ADR-386).
   */
  approvalUnavailable?: boolean;
}

/**
 * How a routine reaches its owner: it asks before running, or it runs and only
 * notifies when it found something new — never both.
 *
 * A routine that asks first always notifies: its proposal IS the notification,
 * so there would be nothing to hold back. The server refuses the pair; the
 * form never lets it be composed — asking first switches the second option off
 * and leaves it unavailable, with the hint saying why.
 *
 * Two properties a keyboard and a screen reader depend on (the pattern of
 * `RefusalSwitches`):
 *
 * - **a hint is a fact ABOUT its option**, attached through `aria-describedby`:
 *   beside the control it is only seen;
 * - **unavailable is said, not removed.** The ruled-out option keeps its tab
 *   stop (`aria-disabled`, never `disabled`) so its hint can say why; what
 *   refuses the change is the handler — the same for « ask first » on a
 *   routine started by calls.
 */
export function RoutineDeliveryFields({
  idPrefix,
  requiresApproval,
  notifyOnlyWhenNew,
  onChange,
  approvalUnavailable = false,
}: RoutineDeliveryFieldsProps) {
  const { t } = useTranslation();
  const approvalId = `${idPrefix}-approval`;
  const quietId = `${idPrefix}-quiet`;
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <Label htmlFor={approvalId}>{t('scheduled_actions.studio.requires_approval')}</Label>
          <p id={`${approvalId}-hint`} className="text-xs text-muted-foreground">
            {t(
              approvalUnavailable
                ? 'scheduled_actions.studio.requires_approval_unavailable'
                : 'scheduled_actions.studio.requires_approval_hint'
            )}
          </p>
        </div>
        <Switch
          id={approvalId}
          checked={requiresApproval}
          aria-disabled={approvalUnavailable || undefined}
          aria-describedby={`${approvalId}-hint`}
          className="aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
          onCheckedChange={asked => {
            if (approvalUnavailable && asked) return;
            onChange({
              requires_approval: asked,
              notify_only_when_new: asked ? false : notifyOnlyWhenNew,
            });
          }}
        />
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <Label htmlFor={quietId}>{t('scheduled_actions.studio.notify_only_when_new')}</Label>
          <p id={`${quietId}-hint`} className="text-xs text-muted-foreground">
            {t(
              requiresApproval
                ? 'scheduled_actions.studio.notify_only_when_new_unavailable'
                : 'scheduled_actions.studio.notify_only_when_new_hint'
            )}
          </p>
        </div>
        <Switch
          id={quietId}
          checked={notifyOnlyWhenNew}
          aria-disabled={requiresApproval || undefined}
          aria-describedby={`${quietId}-hint`}
          className="aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
          onCheckedChange={quiet => {
            if (requiresApproval) return;
            onChange({ requires_approval: requiresApproval, notify_only_when_new: quiet });
          }}
        />
      </div>
    </>
  );
}
