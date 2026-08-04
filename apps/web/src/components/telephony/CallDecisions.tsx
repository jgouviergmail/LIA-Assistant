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

  const prefill = (sentence: string) => () => openChatDeepLink(chatDraftHref(lng, sentence));

  const meetingDraft = t('settings.telephony.decisions.meeting_draft', {
    subject: objective,
    invitee: calleeDisplay,
    when: facts.proposed_datetime ?? '',
    where: facts.location ?? '',
  });

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-amber-300/50 bg-amber-50/50 p-3 dark:border-amber-800/40 dark:bg-amber-950/20">
      <p className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
        {t('settings.telephony.decisions.title')}
      </p>

      {(facts.proposed_datetime || facts.location) && (
        <p className="flex flex-wrap items-baseline gap-2 text-sm text-foreground/90">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          {/* "Proposed", never "booked": the assistant did not accept it. */}
          <span>
            {t('settings.telephony.decisions.proposed', {
              when: facts.proposed_datetime ?? t('settings.telephony.decisions.no_date'),
              where: facts.location ?? t('settings.telephony.decisions.no_place'),
            })}
          </span>
        </p>
      )}

      {facts.additional_costs && (
        <p className="flex flex-wrap items-baseline gap-2 text-sm font-medium text-foreground">
          <CircleDollarSign
            className="h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400"
            aria-hidden="true"
          />
          <span>
            {t('settings.telephony.decisions.extra_cost', { cost: facts.additional_costs })}
          </span>
        </p>
      )}

      {facts.pending_user_decision && (
        <p className="flex flex-wrap items-baseline gap-2 text-sm text-foreground/90">
          <HelpCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span>
            {t('settings.telephony.decisions.pending', {
              question: facts.pending_user_decision,
            })}
          </span>
        </p>
      )}

      {actionable && (facts.proposed_datetime || facts.location) && (
        <button
          type="button"
          onClick={prefill(meetingDraft)}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border/60 bg-card px-2.5 text-xs font-medium text-foreground/90 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <CalendarPlus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('settings.telephony.decisions.plan_meeting')}
        </button>
      )}
    </div>
  );
}
