'use client';

import { useId, useState, type Ref } from 'react';
import { Clock3, FileText, Loader2, Target, Timer } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import { Badge } from '@/components/ui/badge';
import { CallDebrief, CallDebriefActions } from './CallDebrief';
import { CallDecisions, CallDecisionsActions } from './CallDecisions';
import { formatDate, formatEuro } from '@/lib/format';
import { callOutcomeTone, lifecycleTone, relayOutcomeTone } from '@/lib/status-tone';
import { projectCallTimeline } from '@/lib/telephony/timeline';
import { ACTIVE_CALL_STATUSES, type TelephonyCallSummary } from '@/types/telephony';
import type { Language } from '@/i18n/settings';

type TimelineItem = ReturnType<typeof projectCallTimeline>['days'][number]['entries'][number];

function durationLabel(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.round(seconds);
  return whole < 60 ? `${whole} s` : `${Math.floor(whole / 60)} min ${whole % 60} s`;
}

function CallTraits({ call, lng }: { call: TelephonyCallSummary; lng: Language }) {
  const { t } = useTranslation(lng);
  const duration = durationLabel(call.call_seconds);
  return (
    <>
      {duration !== null && (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Timer className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="sr-only">{t('settings.telephony.calls.duration')} </span>
          <span>{duration}</span>
        </span>
      )}
      {call.outcome && (
        <Badge variant={callOutcomeTone(call.outcome)} size="sm">
          {t(`settings.telephony.calls.outcome.${call.outcome}`)}
        </Badge>
      )}
      {call.call_kind !== 'third_party' && (
        <Badge variant="default" size="sm">
          {t(`settings.telephony.calls.kind.${call.call_kind}`)}
        </Badge>
      )}
      {call.call_kind === 'self' && (
        <Badge variant="default" size="sm">
          {t(`settings.telephony.identity.call_mode.${call.call_mode}`)}
        </Badge>
      )}
      {call.relay_outcome && (
        <Badge variant={relayOutcomeTone(call.relay_outcome)} size="sm">
          {t(`settings.telephony.calls.relay.${call.relay_outcome}`)}
        </Badge>
      )}
    </>
  );
}

function CallClock({ entry, lng }: { entry: TimelineItem; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <span className="col-start-1 row-start-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm tabular-nums text-muted-foreground sm:row-span-2 sm:flex-col sm:items-start">
      <span className="inline-flex items-center gap-1.5">
        <Clock3 className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
        {entry.start ? (
          <time
            dateTime={entry.call.created_at}
            title={formatDate(entry.call.created_at, lng, {
              dateStyle: 'full',
              timeStyle: 'short',
            })}
          >
            <span className="sr-only">{t('settings.telephony.calls.start')} </span>
            {entry.start}
          </time>
        ) : (
          <span>{t('settings.telephony.calls.unknown_date')}</span>
        )}
      </span>
      {entry.end && entry.call.completed_at && (
        <span className="inline-flex flex-wrap items-center gap-x-1.5 sm:pl-5">
          <span className="sm:hidden" aria-hidden="true">
            –
          </span>
          <time
            dateTime={entry.call.completed_at ?? undefined}
            title={formatDate(entry.call.completed_at, lng, {
              dateStyle: 'full',
              timeStyle: 'short',
            })}
          >
            <span className="sr-only">{t('settings.telephony.calls.end')} </span>
            {entry.end}
          </time>
          {entry.endDay && <span className="basis-full text-xs">{entry.endDay}</span>}
        </span>
      )}
    </span>
  );
}

export function CallHistoryRow({
  entry,
  lng,
  initiallyOpen = false,
  summaryRef,
}: {
  entry: TimelineItem;
  lng: Language;
  initiallyOpen?: boolean;
  summaryRef?: Ref<HTMLElement>;
}) {
  const { t } = useTranslation(lng);
  const [open, setOpen] = useState(initiallyOpen);
  const id = useId();
  const { call } = entry;
  const active = ACTIVE_CALL_STATUSES.includes(call.status);
  return (
    <li className="min-w-0">
      <details
        open={open}
        onToggle={event => setOpen(event.currentTarget.open)}
        className="min-w-0 bg-background"
      >
        <summary
          ref={summaryRef}
          aria-label={call.callee_display}
          aria-describedby={`${id}-time ${id}-status ${id}-meta`}
          className="grid min-h-14 min-w-0 cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 rounded-lg p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:grid-cols-[8.5rem_minmax(0,1fr)_auto] sm:p-4 [&::-webkit-details-marker]:hidden"
        >
          <span id={`${id}-time`} className="contents">
            <CallClock entry={entry} lng={lng} />
          </span>
          <span
            id={`${id}-status`}
            className="col-start-2 row-start-1 justify-self-end sm:col-start-3"
          >
            <Badge variant={lifecycleTone(call.status)} size="sm">
              {active && (
                <Loader2
                  className="mr-1 size-3 shrink-0 animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              )}
              {t(`settings.telephony.calls.status.${call.status}`)}
            </Badge>
          </span>
          <span className="col-span-2 col-start-1 row-start-2 min-w-0 break-words text-sm font-normal leading-relaxed text-foreground [overflow-wrap:anywhere] sm:col-span-1 sm:col-start-2 sm:row-start-1">
            {call.callee_display}
          </span>
          <span
            id={`${id}-meta`}
            className="col-span-2 col-start-1 row-start-3 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5 sm:col-start-2 sm:row-start-2"
          >
            <CallTraits call={call} lng={lng} />
          </span>
        </summary>
        {open && (
          <div className="min-w-0 space-y-4 bg-card border-t border-border p-3 [overflow-wrap:anywhere] sm:p-4">
            {call.usage && (
              <p className="text-xs text-muted-foreground">
                {t('settings.telephony.calls.usage', {
                  tokens: (call.usage.tokens_in + call.usage.tokens_out).toLocaleString(lng),
                  cost: formatEuro(call.usage.cost_eur, 4, lng),
                })}
              </p>
            )}
            <div className="space-y-2">
              <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <Target className="size-4 shrink-0 text-primary" aria-hidden="true" />
                {t('settings.telephony.calls.objective')}
              </p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{call.objective}</p>
            </div>
            {call.summary && (
              <div className="space-y-2">
                <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <FileText className="size-4 shrink-0 text-primary" aria-hidden="true" />
                  {t('settings.telephony.calls.summary')}
                </p>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{call.summary}</p>
              </div>
            )}
            <CallDecisions
              data={call.structured_data}
              calleeDisplay={call.callee_display}
              objective={call.objective}
              lng={lng}
            />
            {call.debrief && <CallDebrief debrief={call.debrief} lng={lng} />}
            <div className="space-y-3 empty:hidden">
              <CallDecisionsActions
                data={call.structured_data}
                calleeDisplay={call.callee_display}
                objective={call.objective}
                lng={lng}
              />
              {call.debrief && <CallDebriefActions debrief={call.debrief} lng={lng} />}
            </div>
          </div>
        )}
      </details>
    </li>
  );
}
