'use client';

/**
 * What the OTHER party proposed, and what it would take to accept it.
 *
 * The post-call synthesis has always extracted these facts — a date, a place,
 * a surcharge, an option the assistant refused to settle — and the database has
 * always stored them. Nothing showed them: a price increase mentioned on a call
 * placed on the user's behalf existed in `structured_data` and nowhere the
 * person paying it could read it.
 *
 * **Nothing here is accepted, and nothing here accepts.** Every action is a
 * `?draft=`: the sentence lands in the composer, the user reads it and presses
 * Enter, and whatever writes afterwards still meets its own tool-level HITL.
 * A cost or an option proposed by someone else is a claim to arbitrate, never
 * an instruction — which is exactly why the assistant flagged it instead of
 * agreeing to it on the call.
 *
 * The meeting draft is the one that earns the extraction: it carries the
 * subject, the person and the place the call actually produced, so the user
 * reviews a proposal rather than retyping it.
 */

import { CalendarPlus, CircleDollarSign, HelpCircle, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';
import type { StructuredCallData } from '@/types/telephony';

export interface CallDecisionsProps {
  data: StructuredCallData | null | undefined;
  /** Who was called — the invitee of a meeting draft. */
  calleeDisplay: string;
  /** What the call was for — the subject of a meeting draft. */
  objective: string;
  lng: string;
  /** Actions render only where the surface can host them (settings). */
  actionable?: boolean;
}

/**
 * True when the extraction produced something the reader has to arbitrate.
 *
 * `agreed` and `notes` are deliberately absent from the test: they are the
 * RECORD of the call, already covered by the recap above. This block exists
 * for what is still open.
 */
function hasDecisions(data: StructuredCallData): boolean {
  return Boolean(
    data.proposed_datetime || data.location || data.additional_costs || data.pending_user_decision
  );
}

export function CallDecisions({
  data,
  calleeDisplay,
  objective,
  lng,
  actionable = false,
}: CallDecisionsProps) {
  const { t } = useTranslation();
  // Narrowed by control flow, never by a cast: `facts` is a real
  // `StructuredCallData` from here on because the two guards above say so.
  if (!data) return null;
  const facts = data;
  if (!hasDecisions(facts)) return null;

  return (
    <div className="mt-2 min-w-0 space-y-3 rounded-lg border border-amber-300/50 bg-amber-50/50 p-3 dark:border-amber-800/40 dark:bg-amber-950/20">
      <p className="flex items-center gap-2 text-xs font-semibold text-foreground">
        <HelpCircle className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('settings.telephony.decisions.title')}
      </p>

      {(facts.proposed_datetime || facts.location) && (
        <p className="flex items-start gap-2 text-sm text-foreground/90">
          <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
          {/* "Proposed", never "booked": the assistant did not accept it. */}
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {t('settings.telephony.decisions.proposed', {
              when: facts.proposed_datetime ?? t('settings.telephony.decisions.no_date'),
              where: facts.location ?? t('settings.telephony.decisions.no_place'),
            })}
          </span>
        </p>
      )}

      {facts.additional_costs && (
        <p className="flex items-start gap-2 text-sm font-medium text-foreground">
          <CircleDollarSign
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400"
            aria-hidden="true"
          />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {t('settings.telephony.decisions.extra_cost', { cost: facts.additional_costs })}
          </span>
        </p>
      )}

      {facts.pending_user_decision && (
        <p className="flex items-start gap-2 text-sm text-foreground/90">
          <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {t('settings.telephony.decisions.pending', {
              question: facts.pending_user_decision,
            })}
          </span>
        </p>
      )}

      {actionable && (
        <CallDecisionsActions
          data={facts}
          calleeDisplay={calleeDisplay}
          objective={objective}
          lng={lng}
        />
      )}
    </div>
  );
}

/** Same reviewed meeting draft, separately placeable after the call's facts. */
export function CallDecisionsActions({
  data,
  calleeDisplay,
  objective,
  lng,
}: Omit<CallDecisionsProps, 'actionable'>) {
  const { t } = useTranslation();
  if (!data || (!data.proposed_datetime && !data.location)) return null;

  const meetingDraft = t('settings.telephony.decisions.meeting_draft', {
    subject: objective,
    invitee: calleeDisplay,
    when: data.proposed_datetime ?? '',
    where: data.location ?? '',
  });

  return (
    <Button
      type="button"
      onClick={() => openChatDeepLink(chatDraftHref(lng, meetingDraft))}
      className="h-auto min-h-11 w-full justify-start whitespace-normal px-3 py-2.5 text-left text-xs [overflow-wrap:anywhere]"
    >
      <CalendarPlus aria-hidden="true" />
      {t('settings.telephony.decisions.plan_meeting')}
    </Button>
  );
}
