'use client';

/**
 * Recent outbound calls (A6) — the surface the backend was already serving.
 *
 * `GET /telephony/calls` shipped with the telephony domain and was wired to
 * nothing. Once a call was confirmed in the chat, the product went silent: no
 * sign that LIA was dialing, and — if the post-call notification was missed —
 * no way to ever read the outcome, which sat in the database out of reach.
 *
 * What is shown, and what is deliberately not:
 *  - the callee's NAME, the objective, the status, the outcome and the recap —
 *    each call folded, its header saying who, when, how long and how it went;
 *  - never the phone number. The API omits it on purpose (encrypted at rest),
 *    and `TelephonyCallSummary` has no field for it, so it cannot leak here.
 *
 * While a call is in flight the list refreshes on its own. That is a refresh,
 * not a stream: the vendor only sends a POST-call webhook, so there is nothing
 * live to subscribe to and the UI does not pretend there is.
 */

import { Loader2, Phone, PhoneCall } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import { Badge } from '@/components/ui/badge';
import { Disclosure } from '@/components/ui/disclosure';
import { CallDebrief } from '@/components/telephony/CallDebrief';
import { CallDecisions } from '@/components/telephony/CallDecisions';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTelephonyCalls } from '@/hooks/useTelephonyCalls';
import { formatDate, formatEuro } from '@/lib/format';
import { callOutcomeTone, lifecycleTone, relayOutcomeTone } from '@/lib/status-tone';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';
import type { BaseSettingsProps } from '@/types/settings';
import type { Language } from '@/i18n/settings';

/** `62` → `1 min 2 s`, `48` → `48 s`. */
function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole} s`;
  return `${Math.floor(whole / 60)} min ${whole % 60} s`;
}

/**
 * The call's start as two facts, date and time, in the reader's language.
 *
 * `created_at` is when LIA dialled — the API carries no separate answer time.
 * An unreadable instant yields nothing rather than "Invalid Date".
 */
function startFacts(createdAt: string, lng: Language): string[] {
  const started = new Date(createdAt);
  if (Number.isNaN(started.getTime())) return [];
  return [
    formatDate(started, lng, { dateStyle: 'medium' }),
    formatDate(started, lng, { timeStyle: 'short' }),
  ];
}

/**
 * The badges of a call: status, outcome, kind, mode and relay verdict.
 *
 * The status and the outcome are `Badge`s named by `status-tone`
 * (ADR-205/206), not hand-written pills. The previous pill had TWO states —
 * "in flight" or grey — so `completed`, `failed`, `no_answer` and `cancelled`
 * were the same object on screen, and neither pill went through the
 * design-system contrast guard.
 */
function CallBadges({ call, lng }: { call: TelephonyCallSummary; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <span className="flex flex-wrap gap-1.5">
      <Badge variant={lifecycleTone(call.status)} size="sm">
        {t(`settings.telephony.calls.status.${call.status}`)}
      </Badge>
      {call.outcome && (
        <Badge variant={callOutcomeTone(call.outcome)} size="sm">
          {t(`settings.telephony.calls.outcome.${call.outcome}`)}
        </Badge>
      )}
      {/* Phone as a channel: a call WITH the person (or the verification of
          their number) is not an errand for them — the kind says which, and
          the relay verdict says whether their words reached the chat. */}
      {call.call_kind !== 'third_party' && (
        <Badge variant="secondary" size="sm">
          {t(`settings.telephony.calls.kind.${call.call_kind}`)}
        </Badge>
      )}
      {/* ADR-301: a call WITH the person ran Live (every request handed to the
          chat as it was said) or Live direct (relayed at its end) — the mode
          it RAN, which the closing honoured, not today's setting. */}
      {call.call_kind === 'self' && (
        <Badge variant="outline" size="sm">
          {t(`settings.telephony.identity.call_mode.${call.call_mode}`)}
        </Badge>
      )}
      {call.relay_outcome && (
        <Badge variant={relayOutcomeTone(call.relay_outcome)} size="sm">
          {t(`settings.telephony.calls.relay.${call.relay_outcome}`)}
        </Badge>
      )}
    </span>
  );
}

/**
 * One call, folded by default (owner request 2026-10-03).
 *
 * Ten calls unfolded were a wall of recaps. Folded, each is an index entry
 * that still answers the scanning questions — who, when, how long, and how it
 * went (the badges, on their own line so they wrap on a phone) — while the
 * objective, the recap, the decisions, the debrief and the bill wait behind
 * the fold. A call still in flight keeps its spinner in the header.
 */
function CallRow({ call, lng }: { call: TelephonyCallSummary; lng: Language }) {
  const { t } = useTranslation(lng);
  const isActive = ACTIVE_CALL_STATUSES.includes(call.status);
  const facts = startFacts(call.created_at, lng);
  if (call.call_seconds !== null) facts.push(formatDuration(call.call_seconds));

  return (
    <li>
      <Disclosure
        icon={isActive ? Loader2 : Phone}
        iconClassName={isActive ? 'animate-spin' : undefined}
        title={call.callee_display}
        description={facts.length > 0 ? facts.join(' · ') : undefined}
        meta={<CallBadges call={call} lng={lng} />}
      >
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{call.objective}</p>
          {call.summary && <p className="text-sm">{call.summary}</p>}
          {/* T01: the structured debrief, ACTIONABLE here — each follow-up can
              be sent to the chat as an executable intent (ADR-173). */}
          {/* Decisions BEFORE the debrief: a surcharge or an option left open
              is what the reader has to answer, while the lists below are what
              the call produced. Reading order follows what has to be acted on. */}
          <CallDecisions
            data={call.structured_data}
            calleeDisplay={call.callee_display}
            objective={call.objective}
            lng={lng}
            actionable
          />
          {call.debrief && <CallDebrief debrief={call.debrief} lng={lng} actionable />}
          {/* Lot 8: the call's cumulated bill — the same summary the chat meter reads. */}
          {call.usage && (
            <p className="text-px-11 text-muted-foreground/80">
              {t('settings.telephony.calls.usage', {
                tokens: (call.usage.tokens_in + call.usage.tokens_out).toLocaleString(lng),
                cost: formatEuro(call.usage.cost_eur, 4, lng),
              })}
            </p>
          )}
        </div>
      </Disclosure>
    </li>
  );
}

/** The section shows the 10 most recent calls only (owner arbitration
 *  2026-07-30) — the full history stays in the database, out of the way. */
const RECENT_CALLS_LIMIT = 10;

export default function TelephonyCallsSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { calls, hasActiveCall, isLoading, isUnavailable } = useTelephonyCalls(
    true,
    RECENT_CALLS_LIMIT
  );

  // Feature off, or nothing ever dialled: no empty shelf on the settings page.
  if (isUnavailable || (!isLoading && calls.length === 0)) return null;

  return (
    <SettingsSection
      value="telephony-calls"
      title={t('settings.telephony.calls.title')}
      description={t('settings.telephony.calls.description')}
      icon={PhoneCall}
    >
      {/* Polite: a call ending is worth announcing, not worth interrupting. */}
      <div aria-live="polite" className="sr-only">
        {hasActiveCall ? t('settings.telephony.calls.in_flight') : ''}
      </div>
      <ul className="space-y-2">
        {calls.map(call => (
          <CallRow key={call.id} call={call} lng={lng} />
        ))}
      </ul>
    </SettingsSection>
  );
}
