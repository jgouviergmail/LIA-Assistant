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
 *  - the callee's NAME, the objective, the status, the outcome and the recap;
 *  - never the phone number. The API omits it on purpose (encrypted at rest),
 *    and `TelephonyCallSummary` has no field for it, so it cannot leak here.
 *
 * While a call is in flight the list refreshes on its own. That is a refresh,
 * not a stream: the vendor only sends a POST-call webhook, so there is nothing
 * live to subscribe to and the UI does not pretend there is.
 */

import { PhoneCall, Loader2 } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import { Badge } from '@/components/ui/badge';
import { CallDebrief } from '@/components/telephony/CallDebrief';
import { CallDecisions } from '@/components/telephony/CallDecisions';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTelephonyCalls } from '@/hooks/useTelephonyCalls';
import { callOutcomeTone, lifecycleTone } from '@/lib/status-tone';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';
import type { BaseSettingsProps } from '@/types/settings';
import type { Language } from '@/i18n/settings';

/** `62` → `1 min 2 s`, `48` → `48 s`. */
function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole} s`;
  return `${Math.floor(whole / 60)} min ${whole % 60} s`;
}

function CallRow({ call, lng }: { call: TelephonyCallSummary; lng: Language }) {
  const { t } = useTranslation(lng);
  const isActive = ACTIVE_CALL_STATUSES.includes(call.status);
  const started = new Date(call.created_at);

  return (
    <li className="rounded-lg border border-border/60 bg-card/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {isActive && (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" aria-hidden="true" />
        )}
        <span className="font-medium">{call.callee_display}</span>
        {/* The status and the outcome are `Badge`s named by `status-tone`
            (ADR-205/206), not hand-written pills. The previous pill had TWO
            states — "in flight" or grey — so `completed`, `failed`, `no_answer`
            and `cancelled` were the same object on screen, and neither pill
            went through the design-system contrast guard. */}
        <Badge variant={lifecycleTone(call.status)} size="sm">
          {t(`settings.telephony.calls.status.${call.status}`)}
        </Badge>
        {call.outcome && (
          <Badge variant={callOutcomeTone(call.outcome)} size="sm">
            {t(`settings.telephony.calls.outcome.${call.outcome}`)}
          </Badge>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{call.objective}</p>
      {call.summary && <p className="mt-1 text-sm">{call.summary}</p>}
      {/* T01: the structured debrief, ACTIONABLE here — each follow-up can be
          sent to the chat as an executable intent (ADR-173). */}
      {/* Decisions BEFORE the debrief: a surcharge or an option left open is
          what the reader has to answer, while the lists below are what the
          call produced. Reading order follows what has to be acted on. */}
      <CallDecisions
        data={call.structured_data}
        calleeDisplay={call.callee_display}
        objective={call.objective}
        lng={lng}
        actionable
      />
      {call.debrief && <CallDebrief debrief={call.debrief} lng={lng} actionable />}
      <p className="mt-1 text-[11px] text-muted-foreground/80">
        {Number.isNaN(started.getTime())
          ? null
          : started.toLocaleString(lng, { dateStyle: 'short', timeStyle: 'short' })}
        {call.call_seconds !== null && ` · ${formatDuration(call.call_seconds)}`}
      </p>
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
