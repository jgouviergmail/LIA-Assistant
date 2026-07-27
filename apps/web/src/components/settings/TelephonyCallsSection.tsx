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
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTelephonyCalls } from '@/hooks/useTelephonyCalls';
import { cn } from '@/lib/utils';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';
import type { BaseSettingsProps } from '@/types/settings';
import type { Language } from '@/i18n/settings';

/** Tone per outcome — muted by default, never alarming for a normal refusal. */
const OUTCOME_TONE: Record<string, string> = {
  objective_met: 'text-emerald-600 dark:text-emerald-400',
  partial: 'text-amber-600 dark:text-amber-400',
  declined: 'text-muted-foreground',
  unreachable: 'text-muted-foreground',
};

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
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[11px]',
            isActive ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
          )}
        >
          {t(`settings.telephony.calls.status.${call.status}`)}
        </span>
        {call.outcome && (
          <span className={cn('text-[11px] font-medium', OUTCOME_TONE[call.outcome])}>
            {t(`settings.telephony.calls.outcome.${call.outcome}`)}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{call.objective}</p>
      {call.summary && <p className="mt-1 text-sm">{call.summary}</p>}
      <p className="mt-1 text-[11px] text-muted-foreground/80">
        {Number.isNaN(started.getTime())
          ? null
          : started.toLocaleString(lng, { dateStyle: 'short', timeStyle: 'short' })}
        {call.call_seconds !== null && ` · ${formatDuration(call.call_seconds)}`}
      </p>
    </li>
  );
}

export default function TelephonyCallsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { calls, hasActiveCall, isLoading, isUnavailable } = useTelephonyCalls();

  // Feature off, or nothing ever dialled: no empty shelf on the settings page.
  if (isUnavailable || (!isLoading && calls.length === 0)) return null;

  return (
    <SettingsSection
      value="telephony-calls"
      title={t('settings.telephony.calls.title')}
      description={t('settings.telephony.calls.description')}
      icon={PhoneCall}
      collapsible={collapsible}
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
